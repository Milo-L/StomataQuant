import os
import sys
from macos_paths import macos_output_dir
import io
import json
import math
from PyQt5.QtCore import QEventLoop, QTimer, Qt
from PyQt5.QtGui import QPixmap, QImageReader
from PyQt5 import QtCore, QtWidgets, sip
from collections import defaultdict, Counter
from PyQt5.QtWidgets import QApplication, QDialog, QMessageBox, QWidget, QVBoxLayout
from PyQt5.QtCore import QPointF
import csv  # 添加 csv 导入
import glob
from AllDialogs import BatchProcessingDialog, BatchProgressDialog
from InferenceThread import YOLOSegInferenceThread, HeatMapGenerationThread,PolygonProcessThread, BatchInferenceSession
from shape import Shape
from measurements import resolve_scale, ensure_features, refresh_shapes
from task_support import task_manager, wait_for_worker, OperationCancelled, check_cancelled
from inference_support import decode_predictions, shapes_from_predictions, save_polygon_audit
from ImageGraphicsView import ImageGraphicsView
from canvas import process_polygon_data
from point_annotations import batch_points, batch_import_points, require_target
from batch_ui import annotation_batch, checkpoint, exact_annotation_candidates, image_path_key, mark_batch_fit
from safe_io import source_suffix, write_unique_text_atomic, write_text_atomic
from annotation_io import validate_polygon_export, validate_rectangle_export
from geometry import minimum_rectangle_size
import traceback
import ctypes
from functools import cmp_to_key


class InvalidAnnotationData(ValueError):
    pass


# Windows 文件资源管理器风格的自然排序
if os.name == "nt":
    _logical_compare = ctypes.windll.shlwapi.StrCmpLogicalW
    _logical_compare.argtypes = [
        ctypes.c_wchar_p,
        ctypes.c_wchar_p
    ]
    _logical_compare.restype = ctypes.c_int


def compare_filenames(path_a, path_b):
    name_a = os.path.basename(path_a)
    name_b = os.path.basename(path_b)

    if os.name == "nt":
        return _logical_compare(name_a, name_b)

    # 非 Windows 系统备用排序
    a = name_a.casefold()
    b = name_b.casefold()
    return (a > b) - (a < b)

class BatchProcessor:
    def __init__(self, main_window):
        """
        初始化批处理器
        Args:
            main_window: UIMainWindow的实例，提供对主窗口功能的访问
        """
        self.main_window = main_window
        self._ai_session = None
        self.rejected_predictions = 0
        self._ai_model = getattr(main_window, 'model', None)
        
# 在 BatchProcessor 类的 process 方法中添加新选项的处理

    def process(self):
        if getattr(self.main_window, '_batch_running', False):
            return
        tabs = [self.main_window.tabWidget.widget(i) for i in range(self.main_window.tabWidget.count())]
        if len(tabs) < 2:
            QMessageBox.warning(self.main_window, 'Batch Processing', 'Batch Processing requires at least two open images/tabs.')
            return
        dialog = BatchProcessingDialog(self.main_window)
        if dialog.exec_() != QDialog.Accepted:
            return
        options = self.batch_options = dialog.get_options()
        self.batch_heatmap_settings = options.get('heatmap_settings', {})
        names = [name for name in ('ai','filter','group_id_display','class_visibility','show_points','mer','heatmap')
                 if (name in options if name in ('group_id_display','class_visibility') else options.get(name))]
        if not names:
            return
        results = {key: 0 for key in ('success','failed','skipped','canceled')}
        results.update(operations={name: {key: 0 for key in ('success','failed','skipped','canceled')} for name in names}, errors=[])
        progress = BatchProgressDialog(self.main_window)
        progress.set_max_operations(len(tabs)*len(names)); progress.show()
        original_tab = self.main_window.tabWidget.currentWidget()
        self.main_window._batch_running = True
        previous_defer = getattr(self.main_window, '_defer_batch_refresh', False)
        self.main_window._defer_batch_refresh = True
        if hasattr(self.main_window, '_measurement_timer'):
            self.main_window._measurement_timer.stop()
        completed = 0
        self._ai_session = None
        self._ai_model = getattr(self.main_window, 'model', None)
        self.rejected_predictions = 0
        try:
            if 'ai' in names and self._ai_model:
                model_path = getattr(self._ai_model, '_stomataquant_source_path', None)
                if model_path:
                    self._ai_session = BatchInferenceSession(model_path)
                    self._ai_session.start()
            for number, tab in enumerate(tabs):
                if progress.canceled or getattr(self.main_window, '_closing_requested', False):
                    results['canceled'] += len(tabs)-number
                    for name in names:
                        results['operations'][name]['canceled'] += len(tabs)-number
                    break
                index = -1 if sip.isdeleted(tab) else self.main_window.tabWidget.indexOf(tab)
                if index < 0:
                    results['skipped'] += 1
                    for name in names: results['operations'][name]['skipped'] += 1
                    continue
                view = tab.property('graphics_view')
                if not view or not view.canvas:
                    results['skipped'] += 1
                    for name in names: results['operations'][name]['skipped'] += 1
                    continue
                progress.set_tab_info(number+1,len(tabs))
                path = tab.property('file_path')
                progress.update_file(os.path.basename(path or 'Unknown'))
                outcomes = []
                for name in names:
                    QApplication.processEvents()
                    if progress.canceled or getattr(self.main_window, '_closing_requested', False):
                        progress.canceled = True
                        results['operations'][name]['canceled'] += 1
                        outcomes.append('canceled')
                        continue
                    index = -1 if sip.isdeleted(tab) else self.main_window.tabWidget.indexOf(tab)
                    if index < 0 or sip.isdeleted(view) or not view.canvas:
                        results['operations'][name]['skipped'] += 1
                        outcomes.append('skipped')
                        continue
                    if name == 'ai':
                        call = lambda: self._process_ai_operation(index,path,view,progress,results)
                    elif name == 'filter':
                        call = lambda: self._process_filter_operation(index,view,options[name],progress,results)
                    elif name == 'group_id_display':
                        call = lambda: self._process_group_id_display(index,view,options[name],progress)
                    elif name == 'class_visibility':
                        call = lambda: self._process_class_visibility(index,view,options[name],progress)
                    else:
                        methods = {'show_points':self._process_show_points_operation, 'mer':self._process_mer_operation,
                                   'heatmap':self._process_heatmap_operation}
                        call = lambda: methods[name](index,view,progress,results)
                    outcomes.append(self._run_operation(name,call,progress,results,number))
                    completed += 1; progress.update_overall_progress(completed)
                state = self._tab_outcome(outcomes)
                results[state] += 1
                if not sip.isdeleted(view) and view.canvas:
                    view.canvas.shapesChanged.emit()
                    view.canvas.update()
        finally:
            if self._ai_session is not None:
                self._ai_session.close()
                self._ai_session = None
            self.main_window._batch_running = False
            if original_tab is not None and not sip.isdeleted(original_tab) and self.main_window.tabWidget.indexOf(original_tab) >= 0:
                self.main_window.tabWidget.setCurrentWidget(original_tab)
            self.main_window._defer_batch_refresh = previous_defer
            if not previous_defer:
                self.main_window.measurement_controller.refresh_tabs()
                index = self.main_window.tabWidget.currentIndex()
                self.main_window.update_list_on_tab_changed(index)
                self.main_window.update_zoom_on_tab_change(index)
                self.main_window.update_undo_button()
                self.main_window.update_actions_inToolBar()
            mark_batch_fit(self.main_window)
            progress.allow_close(); progress.close(); progress.deleteLater()
            self.last_results = results
            self.main_window._last_batch_results = results
            if not getattr(self.main_window, '_closing_requested', False):
                self._display_results_summary(len(tabs),results,options)

    def _notify_canvas(self, canvas):
        # process() emits once per target after all operations; standalone calls still notify.
        if not getattr(self.main_window, '_defer_batch_refresh', False):
            canvas.update()
            canvas.shapesChanged.emit()

    @staticmethod
    def _tab_outcome(outcomes):
        for state in ('canceled','failed','success'):
            if state in outcomes:
                return state
        return 'skipped'

    def _run_operation(self, name, call, progress, results, tab_number):
        counts = results['operations'][name]
        before = dict(counts)
        reported = None
        try:
            reported = call()
        except OperationCancelled:
            counts['canceled'] = counts.get('canceled',0)+1
        except Exception as error:
            counts['failed'] += 1
            progress.update_status(str(error))
        changes = [state for state in ('canceled','failed','success','skipped') if counts.get(state,0)>before.get(state,0)]
        if not changes:
            state = reported if isinstance(reported, str) and reported in counts else 'failed'
            counts[state] += 1
            changes = [state]
            if state == 'failed':
                progress.update_status('Operation did not report a successful result.')
        outcome = self._tab_outcome(changes)
        if outcome == 'failed':
            results['errors'].append({'tab':tab_number+1,'operation':name,'error':getattr(progress,'last_status','Operation failed')})
        return outcome

    def _process_class_visibility(self, tab_index, graphics_view, class_visibility, progress_dialog):
        """处理类别可见性设置"""
        try:
            progress_dialog.update_operation("Applying class visibility settings")
            progress_dialog.update_operation_progress(0)
            
            canvas = graphics_view.canvas
            shapes = canvas.shapes
            
            # 应用类别可见性设置
            visibility_changed = False
            last_percent = -1
            for i, shape in enumerate(shapes):
                if hasattr(shape, 'classnum') and shape.classnum in class_visibility:
                    old_visibility = shape.visible
                    shape.visible = class_visibility[shape.classnum]
                    if old_visibility != shape.visible:
                        visibility_changed = True
                        shape._dirty = True  # 标记为脏以确保重绘
                
                # 更新进度
                percent = int((i+1) * 100 / len(shapes))
                if percent != last_percent:
                    progress_dialog.update_operation_progress(percent)
                    last_percent = percent
            
            if visibility_changed:
                # 更新画布
                self._notify_canvas(canvas)
                
                # 记录操作状态到进度对话框
                progress_dialog.update_status(f"Tab {tab_index + 1}: Applied class visibility settings")
            
            progress_dialog.update_operation_progress(100)
            return 'success' if any(getattr(s, 'classnum', None) in class_visibility for s in shapes) else 'skipped'
        except Exception as e:
            progress_dialog.update_status(f"Error setting class visibility in tab {tab_index + 1}: {str(e)}")
            raise
    # 添加Group ID显示处理方法
    def _process_group_id_display(self, tab_index, graphics_view, display_option, progress_dialog):
        """处理Group ID显示设置"""
        try:
            canvas = graphics_view.canvas
            shapes = canvas.shapes
            
            # 先设置全局状态，确保后续形状继承此设置
            if hasattr(self.main_window, '_global_show_group_id'):
                self.main_window._global_show_group_id = (display_option == "show")
                
            # 然后为每个形状单独设置状态
            for shape in shapes:
                if display_option == "show":
                    if hasattr(shape, 'show_group_id'):
                        shape.show_group_id()
                else:
                    if hasattr(shape, 'hide_group_id'):
                        shape.hide_group_id()
            
            # 强制更新画布
            for shape in shapes:
                shape._dirty = True  # 确保每个形状都被标记为脏
            
            # 立即更新画布以显示变化
            self._notify_canvas(canvas)
            
            # 记录操作状态到进度对话框
            progress_dialog.update_status(f"Tab {tab_index + 1}: Group ID display set to '{display_option}'")
            return 'success' if shapes else 'skipped'
        except Exception as e:
            progress_dialog.update_status(f"Error setting group ID display in tab {tab_index + 1}: {str(e)}")
            raise
    # 添加显示点操作处理方法
    def _process_show_points_operation(self, tab_index, graphics_view, progress_dialog, results):
        """处理转换为点的操作"""
        try:
            progress_dialog.update_operation("Converting shapes to points")
            progress_dialog.update_operation_progress(0)
            
            canvas = graphics_view.canvas
            shapes = [s for s in canvas.shapes if s.visible]
            
            if shapes:
                # 保存初始状态用于撤销
                canvas.save_state()
                
                # 将每个可见形状转换为点
                shapes_changed = False
                for i, shape in enumerate(shapes):
                    progress_dialog.update_operation_progress(int((i+1) * 100 / len(shapes)))
                    # 修正方法名，使用正确的convert_to_point_shape方法
                    if hasattr(shape, 'convert_to_point_shape'):
                        shape.convert_to_point_shape()
                        shapes_changed = True
                
                if shapes_changed:
                    # 更新画布
                    self._notify_canvas(canvas)
                    
                progress_dialog.update_operation_progress(100)
                results["operations"]["show_points"]["success"] += 1
            else:
                progress_dialog.update_status(f"No visible shapes in tab {tab_index + 1}")
                results["operations"]["show_points"]["skipped"] = results["operations"]["show_points"].get("skipped", 0) + 1
        
        except Exception as e:
            progress_dialog.update_status(f"Error in tab {tab_index + 1} show points operation: {str(e)}")
            results["operations"]["show_points"]["failed"] += 1
        
    def _process_ai_operation(self, tab_index, file_path, graphics_view, progress_dialog, results):
        progress_dialog.update_operation('Running YOLO Inference')
        if self._ai_model is not getattr(self.main_window, 'model', None):
            if self._ai_session is not None:
                self._ai_session.close()
                self._ai_session = None
            raise ValueError('The model changed during Batch; start a new Batch with the selected model.')
        if not getattr(self.main_window,'model',None):
            raise ValueError('No model loaded. Please load a model before AI inference.')
        settings = dict(self.main_window.inference_settings or {})
        manager = task_manager(self.main_window)
        task = manager.begin(self.main_window.tabWidget.widget(tab_index),'inference',settings=settings)
        try:
            worker = YOLOSegInferenceThread(self.main_window.model,file_path,settings,self.main_window,
                                            batch_session=self._ai_session)
            predictions, path, error = wait_for_worker(manager,task,worker,worker.inferenceFinished,
                                                       lambda: progress_dialog.canceled)
            if error:
                raise error if isinstance(error,Exception) else RuntimeError(error)
            shapes = self._process_yolo_results(predictions,path,graphics_view.canvas,task,progress_dialog)
            state = 'success' if shapes else 'skipped'
            results['operations']['ai'][state] = results['operations']['ai'].get(state,0)+1
            progress_dialog.update_operation_progress(100)
        finally:
            manager.finish(task)
    
    def _process_filter_operation(self, tab_index, graphics_view, filter_type, progress_dialog, results):
        """处理过滤操作"""
        try:
            if filter_type:
                progress_dialog.update_operation(f"Applying filter: {filter_type}")
                progress_dialog.update_operation_progress(0)
                
                canvas = graphics_view.canvas
                if not canvas.shapes:
                    return 'skipped'
                image_size = canvas.image_size
                image_width = image_size.width()
                image_height = image_size.height()
                tolerance = 3
                
                # 保存初始状态用于撤销
                canvas.save_state()
                
                shapes_to_delete = []
                for shape in canvas.shapes:
                    bounding_rect = shape.get_bounding_rect()
                    if filter_type == "all_edges" and (
                            bounding_rect.left() <= tolerance or
                            bounding_rect.right() >= image_width - tolerance or
                            bounding_rect.top() <= tolerance or
                            bounding_rect.bottom() >= image_height - tolerance):
                        shapes_to_delete.append(shape)
                    elif filter_type == "top_left" and (
                            bounding_rect.left() <= tolerance or
                            bounding_rect.top() <= tolerance):
                        shapes_to_delete.append(shape)
                    elif filter_type == "right_bottom" and (
                            bounding_rect.right() >= image_width - tolerance or
                            bounding_rect.bottom() >= image_height - tolerance):
                        shapes_to_delete.append(shape)
                
                # 删除形状
                for shape in shapes_to_delete:
                    canvas.shapes.remove(shape)
                # 更新画布和状态
                canvas.update()
                progress_dialog.update_operation_progress(100)
                results["operations"]["filter"]["success"] += 1
        
        except Exception as e:
            progress_dialog.update_status(f"Error in tab {tab_index + 1} filter operation: {str(e)}")
            results["operations"]["filter"]["failed"] += 1

    
# 修改 _process_mer_operation 方法

    def _process_mer_operation(self, tab_index, graphics_view, progress_dialog, results):
        """Create MERs for valid polygons; report invalid ones per shape."""
        progress_dialog.update_operation('Calculating Minimum Enclosing Rectangle')
        progress_dialog.update_operation_progress(0)
        canvas = graphics_view.canvas
        polygons = [s for s in canvas.shapes if s.visible and s.shape_type == 'polygon']
        if not polygons:
            results['operations']['mer']['skipped'] += 1
            return
        created, sources, errors = [], [], []
        for index, shape in enumerate(polygons):
            if index % 32 == 0:
                QApplication.processEvents()
                check_cancelled(lambda: progress_dialog.canceled
                                or getattr(self.main_window, '_closing_requested', False)
                                or sip.isdeleted(graphics_view) or graphics_view.canvas is not canvas)
            try:
                mer = shape.calculate_minimum_rotated_rectangle(
                    minimum_rectangle_size(canvas.image_size.width(), canvas.image_size.height()))
                if mer is None:
                    raise ValueError('Cannot create a valid MER')
                created.append(mer)
                sources.append(shape)
            except Exception as error:
                errors.append(f'{shape.label} / Group ID {shape.group_id}: {error}')
            progress_dialog.update_operation_progress(int((index + 1) * 100 / len(polygons)))
        if created:
            canvas.save_state()
            canvas.shapes.extend(created)
            if self.batch_options.get('hide_original_polygons', False):
                for shape in sources:
                    shape.visible = False
            canvas.update()
            results['operations']['mer']['success'] += 1
        else:
            results['operations']['mer']['skipped'] += 1
        if errors:
            results.setdefault('shape_errors', []).extend(
                f'Tab {tab_index + 1} / MER / {message}' for message in errors)
            progress_dialog.update_status(f'{len(errors)} polygon(s) skipped during MER; see Batch summary.')
        progress_dialog.update_operation_progress(100)

    def _process_heatmap_operation(self, tab_index, graphics_view, progress_dialog, results):
        progress_dialog.update_operation('Generating heatmap')
        shapes = [s for s in graphics_view.canvas.shapes if s.visible and s.shape_type=='polygon']
        if not shapes:
            results['operations']['heatmap']['skipped'] = results['operations']['heatmap'].get('skipped',0)+1
            return
        scale_info = resolve_scale(self.main_window,graphics_view)
        for shape in shapes:
            ensure_features(shape,scale_info,force=True)
        settings = getattr(self,'batch_heatmap_settings',{}) or getattr(self.main_window,'heatmap_settings',{})
        tab = self.main_window.tabWidget.widget(tab_index)
        manager = task_manager(self.main_window); task = manager.begin(tab,'heatmap')
        try:
            worker = HeatMapGenerationThread(graphics_view.pixmap_item.pixmap().toImage(),shapes,
                settings.get('feature','Area'),settings.get('colormap','viridis'),
                settings.get('output_path',
                             macos_output_dir('Heatmaps') if sys.platform == 'darwin'
                             else os.path.join(os.getcwd(),'Heatmaps')),
                task.file_path,scale_info,self.main_window)
            path,error = wait_for_worker(manager,task,worker,worker.heatmapGenerated,lambda: progress_dialog.canceled)
            if error:
                raise error if isinstance(error,Exception) else RuntimeError(error)
            if not path:
                raise ValueError('Heatmap output was not produced')
            results['operations']['heatmap']['success'] += 1
            progress_dialog.update_status(f'Heatmap saved: {path}')
            progress_dialog.update_operation_progress(100)
        finally:
            manager.finish(task)
    
# 修改_process_yolo_results方法

    def _process_yolo_results(self, results, file_path, canvas, task=None, progress_dialog=None):
        settings = task.settings if task else (self.main_window.inference_settings or {})
        output_dir = settings.get('save_path',
                                  macos_output_dir('Inference_OutPut') if sys.platform == 'darwin'
                                  else os.path.join(os.getcwd(),'Inference_OutPut'))
        records, polygons = decode_predictions(results,output_dir)
        processed = {}
        if polygons:
            size = canvas.image_size
            if task is not None:
                worker = PolygonProcessThread(polygons,size.width(),size.height(),records,self.main_window)
                processed, records, error = wait_for_worker(task_manager(self.main_window),task,worker,
                    worker.processingFinished,lambda: progress_dialog.canceled)
                if error:
                    raise error if isinstance(error,Exception) else RuntimeError(error)
            else:
                processed = process_polygon_data(polygons,size.width(),size.height())
        if task is not None:
            check_cancelled(lambda: not task_manager(self.main_window).valid(task))
        rejected = save_polygon_audit(processed,file_path,output_dir)
        self.rejected_predictions = getattr(self, 'rejected_predictions', 0) + len(rejected)
        shapes = shapes_from_predictions(records,processed,canvas)
        if shapes:
            canvas.save_state()
            canvas.shapes.extend(shapes)
            canvas.set_mode('edit')
            if not getattr(self.main_window, '_defer_batch_refresh', False):
                canvas.update(); canvas.shapesChanged.emit()
        return shapes

    def _display_results_summary(self, tab_count, results, options):
        lines = ['Batch Processing Results:', f'Total tabs: {tab_count}']
        lines.extend(f'{key.title()}: {results[key]}' for key in ('success','failed','skipped','canceled'))
        for name,counts in results['operations'].items():
            lines.append(name + ': ' + ', '.join(f'{value} {key}' for key,value in counts.items()))
        if getattr(self, 'rejected_predictions', 0):
            lines.append(f'Invalid predicted polygons skipped: {self.rejected_predictions}. See postprocess audit.')
        for error in results.get('errors',[])[:20]:
            lines.append(f"Tab {error['tab']} / {error['operation']}: {error['error']}")
        for error in results.get('shape_errors', [])[:20]:
            lines.append(error)
        QMessageBox.information(self.main_window,'Batch Processing Complete','\n'.join(lines))

# BatchFeatureExporter 类
class BatchFeatureExporter:
    def __init__(self, main_window):
        """
        初始化批量特征导出器
        Args:
            main_window: UIMainWindow的实例
        """
        self.main_window = main_window

    def export_features(self, shape_type):
        """
        导出指定类型形状的特征
        Args:
            shape_type: 形状类型 ('polygon', 'rotated_rectangle', 'rectangle', 'point')
        """
        tab_count = self.main_window.tabWidget.count()
        if tab_count == 0:
            QtWidgets.QMessageBox.warning(self.main_window, "Export Features", "No image tabs open.")
            return

        # 获取保存路径
        default_filename = f"Batch_Export_{shape_type}_Features.csv"
        file_path, _ = QtWidgets.QFileDialog.getSaveFileName(
            self.main_window, 
            f"Export {shape_type} Features", 
            default_filename, 
            "CSV Files (*.csv);;All Files (*)"
        )

        if not file_path:
            return

        # 创建进度对话框
        progress = QtWidgets.QProgressDialog(f"Exporting {shape_type} features...", "Cancel", 0, tab_count, self.main_window)
        progress.setWindowTitle("Batch Export Progress")
        progress.setWindowModality(QtCore.Qt.WindowModal)
        progress.setMinimumDuration(0)
        progress.setValue(0)

        all_data = []
        from measurement_rows import HEADERS
        fieldnames = {header.split(' (')[0] for header in HEADERS[shape_type][2:]}
        fieldnames.update(('Label', 'Group ID'))
        base_fields = ['File Path', 'File Name']

        try:
            for i in range(tab_count):
                if progress.wasCanceled():
                    return
                
                progress.setValue(i)
                tab = self.main_window.tabWidget.widget(i)
                
                # 获取文件信息
                file_path_img = tab.property("file_path")
                file_name = os.path.basename(file_path_img) if file_path_img else f"Tab {i+1}"
                
                # 获取图形视图和画布
                graphics_view = tab.property("graphics_view")
                if not graphics_view or not graphics_view.canvas:
                    continue
                
                canvas = graphics_view.canvas
                # 筛选特定类型的形状
                shapes = [s for s in canvas.shapes if s.shape_type == shape_type and s.visible]
                
                if not shapes:
                    continue

                # 确定比例尺信息
                scale_info = None
                from measurements import resolve_scale
                scale_info = resolve_scale(self.main_window, graphics_view)
                # 提取特征
                for shape_index, shape in enumerate(shapes):
                    if shape_index % 32 == 0:
                        QApplication.processEvents()
                        if progress.wasCanceled() or getattr(self.main_window, '_closing_requested', False):
                            return
                        if sip.isdeleted(tab) or self.main_window.tabWidget.indexOf(tab) < 0:
                            raise ValueError('Export target image was closed.')
                    try:
                        ensure_features(shape, scale_info)
                        shape.measurement_error = None
                    except Exception as error:
                        shape.feature_results = {}
                        shape.measurement_error = str(error)
                    if not shape.feature_results and not shape.measurement_error:
                        shape.measurement_error = 'No measurement result'

                    # 收集数据
                    if shape.feature_results or shape.measurement_error:
                        row_data = {
                            'File Path': file_path_img,
                            'File Name': file_name,
                            'Label': shape.label,
                            'Group ID': shape.group_id,
                            'Measurement Status': 'Failed' if shape.measurement_error else 'OK',
                            'Measurement Error': shape.measurement_error or ''
                        }
                        # 将特征结果合并到行数据中
                        row_data.update(shape.feature_results)
                        row_data['Measurement Unit'] = (scale_info or {}).get('unit', 'pixel')
                        row_data['Scale (unit/pixel)'] = (scale_info or {}).get('scale', 1.0)
                        row_data['Coordinate Unit'] = 'pixel'
                        all_data.append(row_data)
                        # 收集所有出现的字段名
                        fieldnames.update(shape.feature_results.keys())

            progress.setValue(tab_count)

            if not all_data:
                QtWidgets.QMessageBox.information(self.main_window, "Export Features", f"No {shape_type} shapes found to export.")
                return

            # 排序字段名：基础字段在前，其他字段按字母顺序排列
            sorted_fieldnames = base_fields + [f for f in sorted(list(fieldnames)) if f not in base_fields]
            sorted_fieldnames += ['Measurement Status', 'Measurement Error']
            sorted_fieldnames += ['Measurement Unit', 'Scale (unit/pixel)', 'Coordinate Unit']
            for row_data in all_data:
                for field in fieldnames:
                    row_data.setdefault(field, 'NA')

            # 写入CSV
            with io.StringIO(newline='') as csvfile:
                writer = csv.DictWriter(csvfile, fieldnames=sorted_fieldnames)
                writer.writeheader()
                writer.writerows(all_data)
                write_text_atomic(file_path, csvfile.getvalue(), encoding='utf-8-sig')

            QtWidgets.QMessageBox.information(self.main_window, "Export Successful", f"Successfully exported features to:\n{file_path}")

        except Exception as e:
            QtWidgets.QMessageBox.critical(self.main_window, "Export Error", f"An error occurred: {str(e)}")
        finally:
            progress.close()
            if hasattr(self.main_window, 'measurement_controller'):
                self.main_window.measurement_controller.refresh_tabs()
            mark_batch_fit(self.main_window)

class BatchExporter:
    def export_points(self):
        """Export native Point shapes from every open image, including empty TXT files."""
        return batch_points(self.main_window)

    def __init__(self, main_window):
        """
        初始化批量导出器
        Args:
            main_window: UIMainWindow的实例，提供对主窗口功能的访问
        """
        self.main_window = main_window
        
    @annotation_batch(restore_original=True)
    def export_polygons(self):
        """批量导出所有标签页中的多边形形状"""
        # 获取所有打开的标签页
        tabs = [self.main_window.tabWidget.widget(i) for i in range(self.main_window.tabWidget.count())]
        tab_count = len(tabs)
        source_counts = Counter(os.path.splitext(os.path.basename(tab.property('file_path') or ''))[0].casefold()
                                for tab in tabs)
        if tab_count == 0:
            QtWidgets.QMessageBox.warning(self.main_window, "Batch Export", "No image tabs open. Please open some images first.")
            return
            
        # 让用户选择导出目录
        export_dir = QtWidgets.QFileDialog.getExistingDirectory(
            self.main_window, "Select Export Directory", "",
            QtWidgets.QFileDialog.ShowDirsOnly | QtWidgets.QFileDialog.DontResolveSymlinks
        )
        
        if not export_dir:
            return

        # 创建导出子目录
        polygon_dir = os.path.join(export_dir, "StomataQuant Exported Polygon Annotations")
        os.makedirs(polygon_dir, exist_ok=True)
        
        # 创建进度对话框
        progress_dialog = QtWidgets.QProgressDialog("Exporting polygon annotations...", "Cancel", 0, tab_count, self.main_window)
        progress_dialog.setWindowTitle("Batch Export Progress")
        progress_dialog.setWindowModality(QtCore.Qt.WindowModal)
        progress_dialog.setMinimumDuration(0)
        progress_dialog.setValue(0)
        self.main_window._annotation_batch.progress = progress_dialog
        
        # 保存当前标签页索引
        current_tab_index = self.main_window.tabWidget.currentIndex()
        
        # 统计信息
        exported_count = 0
        skipped_count = 0
        failures = []
        
        try:
            for tab_index in range(tab_count):
                # 检查用户是否取消
                if progress_dialog.wasCanceled():
                    break
                    
                # 设置进度
                progress_dialog.setValue(tab_index)
                progress_dialog.setLabelText(f"Exporting tab {tab_index + 1}/{tab_count}...")
                
                # 切换到当前标签页
                # The target is bound directly; do not activate its GUI.
                QtWidgets.QApplication.processEvents()  # 确保UI更新
                
                # 获取当前标签页信息
                tab = tabs[tab_index]
                if sip.isdeleted(tab) or self.main_window.tabWidget.indexOf(tab) < 0:
                    skipped_count += 1
                    continue
                file_path = tab.property("file_path")
                file_name = os.path.basename(file_path) if file_path else f"tab_{tab_index + 1}"
                
                # 获取当前标签页的图形视图和画布
                graphics_view = tab.property("graphics_view")
                if not graphics_view or not graphics_view.canvas:
                    skipped_count += 1
                    continue
                    
                canvas = graphics_view.canvas
                shapes = canvas.shapes
                
                # 检查是否有多边形形状

                polygon_shapes = [s for s in shapes if s.shape_type == "polygon" and s.visible]

                if not polygon_shapes:
                    skipped_count += 1
                    continue
                    
                # 生成导出文件名
                export_filename = f"Polygon_Annotation_Batch_Exported_by_StomataQuant_{os.path.splitext(file_name)[0]}.txt"
                if file_path and source_counts[os.path.splitext(file_name)[0].casefold()] > 1:
                    export_filename = export_filename[:-4] + '__' + source_suffix(file_path) + '.txt'
                
                # 导出多边形
                try:
                    with io.StringIO() as f:
                        image_width = canvas.image_size.width()
                        image_height = canvas.image_size.height()
                        
                        for shape_index, shape in enumerate(polygon_shapes):
                            if shape_index % 256 == 0:
                                checkpoint(self.main_window, tab, canvas)
                            # YOLO格式: <class> <x1> <y1> <x2> <y2> ... <xn> <yn>
                            points_str = ""
                            for point in shape.pointslist:
                                # 归一化坐标
                                norm_x = point.x() / image_width
                                norm_y = point.y() / image_height
                                points_str += f" {norm_x:.6f} {norm_y:.6f}"
                                
                            # 写入YOLO格式的行
                            f.write(f"{shape.classnum}{points_str}\n")
                            
                        content = f.getvalue()
                    validate_polygon_export(content, image_width, image_height, export_filename,
                                            polygon_shapes)
                    checkpoint(self.main_window, tab, canvas)
                    write_unique_text_atomic(polygon_dir, export_filename, file_path, content)
                    exported_count += 1
                except OperationCancelled:
                    raise
                except Exception as e:
                    print(f"Error exporting polygons from tab {tab_index + 1}: {str(e)}")
                    failures.append(f"Tab {tab_index + 1} ({file_name}): {e}")
                
                # 更新进度
                progress_dialog.setValue(tab_index + 1)
                QtWidgets.QApplication.processEvents()  # 确保UI更新
                
            # 恢复到原来的标签页
            # Original target restoration is handled by the batch session.
            
            # 关闭进度对话框
            progress_dialog.close()
            
            # 显示结果消息
            if exported_count > 0:
                QtWidgets.QMessageBox.information(
                    self.main_window,
                    "Export Complete",
                    f"Successfully exported polygon annotations from {exported_count} tabs.\n"
                    f"Skipped {skipped_count} tabs (no polygon shapes or unavailable).\n"
                    f"Failed to export {len(failures)} tabs.\n" + '\n'.join(failures) + "\n\n"
                    f"Files saved to: {polygon_dir}"
                )
            else:
                QtWidgets.QMessageBox.warning(
                    self.main_window,
                    "Export Complete",
                    f"No polygon annotations were exported.\n"
                    f"{skipped_count} tabs have no polygon shapes or are unavailable.\n"
                    f"Failed to export {len(failures)} tabs.\n" + '\n'.join(failures)
                )
                
        except OperationCancelled:
            raise
        except Exception as e:
            progress_dialog.close()
            QtWidgets.QMessageBox.critical(
                self.main_window,
                "Export Error",
                f"An error occurred during batch export: {str(e)}"
            )
            
    @annotation_batch(restore_original=True)
    def export_rectangles(self):
        """批量导出所有标签页中的矩形形状"""
        # 获取所有打开的标签页
        tabs = [self.main_window.tabWidget.widget(i) for i in range(self.main_window.tabWidget.count())]
        tab_count = len(tabs)
        source_counts = Counter(os.path.splitext(os.path.basename(tab.property('file_path') or ''))[0].casefold()
                                for tab in tabs)
        if tab_count == 0:
            QtWidgets.QMessageBox.warning(self.main_window, "Batch Export", "No image tabs open. Please open some images first.")
            return
            
        # 让用户选择导出目录
        export_dir = QtWidgets.QFileDialog.getExistingDirectory(
            self.main_window, "Select Export Directory", "",
            QtWidgets.QFileDialog.ShowDirsOnly | QtWidgets.QFileDialog.DontResolveSymlinks
        )
        
        if not export_dir:
            return

        # 创建导出子目录
        rectangle_dir = os.path.join(export_dir, "StomataQuant Exported Rectangle Annotations")
        os.makedirs(rectangle_dir, exist_ok=True)
        
        # 创建进度对话框
        progress_dialog = QtWidgets.QProgressDialog("Exporting rectangle annotations...", "Cancel", 0, tab_count, self.main_window)
        progress_dialog.setWindowTitle("Batch Export Progress")
        progress_dialog.setWindowModality(QtCore.Qt.WindowModal)
        progress_dialog.setMinimumDuration(0)
        progress_dialog.setValue(0)
        self.main_window._annotation_batch.progress = progress_dialog
        
        # 保存当前标签页索引
        current_tab_index = self.main_window.tabWidget.currentIndex()
        
        # 统计信息
        exported_count = 0
        skipped_count = 0
        failures = []
        
        try:
            for tab_index in range(tab_count):
                # 检查用户是否取消
                if progress_dialog.wasCanceled():
                    break
                    
                # 设置进度
                progress_dialog.setValue(tab_index)
                progress_dialog.setLabelText(f"Exporting tab {tab_index + 1}/{tab_count}...")
                
                # 切换到当前标签页
                # The target is bound directly; do not activate its GUI.
                QtWidgets.QApplication.processEvents()  # 确保UI更新
                
                # 获取当前标签页信息
                tab = tabs[tab_index]
                if sip.isdeleted(tab) or self.main_window.tabWidget.indexOf(tab) < 0:
                    skipped_count += 1
                    continue
                file_path = tab.property("file_path")
                file_name = os.path.basename(file_path) if file_path else f"tab_{tab_index + 1}"
                
                # 获取当前标签页的图形视图和画布
                graphics_view = tab.property("graphics_view")
                if not graphics_view or not graphics_view.canvas:
                    skipped_count += 1
                    continue
                    
                canvas = graphics_view.canvas
                shapes = canvas.shapes
                
                # 检查是否有矩形形状
                rectangle_shapes = [s for s in shapes if s.shape_type == "rectangle"and s.visible]
                
                if not rectangle_shapes:
                    skipped_count += 1
                    continue
                    
                # 生成导出文件名
                # export_filename = os.path.splitext(file_name)[0] + "_rectangle.txt"
                export_filename = f"Rectangle_Annotation_Batch_Exported_by_StomataQuant_{os.path.splitext(file_name)[0]}.txt"
                if file_path and source_counts[os.path.splitext(file_name)[0].casefold()] > 1:
                    export_filename = export_filename[:-4] + '__' + source_suffix(file_path) + '.txt'
                
                # 导出矩形
                try:
                    with io.StringIO() as f:
                        image_width = canvas.image_size.width()
                        image_height = canvas.image_size.height()
                        
                        for shape_index, shape in enumerate(rectangle_shapes):
                            if shape_index % 256 == 0:
                                checkpoint(self.main_window, tab, canvas)
                            if len(shape.pointslist) == 2:
                                # 获取两个点
                                p1 = shape.pointslist[0]
                                p2 = shape.pointslist[1]
                                
                                # 计算中心点和宽高
                                center_x = (p1.x() + p2.x()) / 2.0
                                center_y = (p1.y() + p2.y()) / 2.0
                                width = abs(p2.x() - p1.x())
                                height = abs(p2.y() - p1.y())
                                
                                # 归一化坐标
                                norm_center_x = center_x / image_width
                                norm_center_y = center_y / image_height
                                norm_width = width / image_width
                                norm_height = height / image_height
                                
                                # 写入YOLO格式的行
                                f.write(f"{shape.classnum} {norm_center_x:.6f} {norm_center_y:.6f} {norm_width:.6f} {norm_height:.6f}\n")
                                
                        content = f.getvalue()
                    validate_rectangle_export(rectangle_shapes, content, 'rectangle',
                                              image_width, image_height, export_filename)
                    checkpoint(self.main_window, tab, canvas)
                    write_unique_text_atomic(rectangle_dir, export_filename, file_path, content)
                    exported_count += 1
                except OperationCancelled:
                    raise
                except Exception as e:
                    print(f"Error exporting rectangles from tab {tab_index + 1}: {str(e)}")
                    failures.append(f"Tab {tab_index + 1} ({file_name}): {e}")
                
                # 更新进度
                progress_dialog.setValue(tab_index + 1)
                QtWidgets.QApplication.processEvents()  # 确保UI更新
                
            # 恢复到原来的标签页
            # Original target restoration is handled by the batch session.
            
            # 关闭进度对话框
            progress_dialog.close()
            
            # 显示结果消息
            if exported_count > 0:
                QtWidgets.QMessageBox.information(
                    self.main_window,
                    "Export Complete",
                    f"Successfully exported rectangle annotations from {exported_count} tabs.\n"
                    f"Skipped {skipped_count} tabs (no rectangle shapes or unavailable).\n"
                    f"Failed to export {len(failures)} tabs.\n" + '\n'.join(failures) + "\n\n"
                    f"Files saved to: {rectangle_dir}"
                )
            else:
                QtWidgets.QMessageBox.warning(
                    self.main_window,
                    "Export Complete",
                    f"No rectangle annotations were exported.\n"
                    f"{skipped_count} tabs have no rectangle shapes or are unavailable.\n"
                    f"Failed to export {len(failures)} tabs.\n" + '\n'.join(failures)
                )
                
        except OperationCancelled:
            raise
        except Exception as e:
            progress_dialog.close()
            QtWidgets.QMessageBox.critical(
                self.main_window,
                "Export Error",
                f"An error occurred during batch export: {str(e)}"
            )
            
    @annotation_batch(restore_original=True)
    def export_rotated_rectangles(self):
        """批量导出所有标签页中的旋转矩形形状"""
        # 获取所有打开的标签页
        tabs = [self.main_window.tabWidget.widget(i) for i in range(self.main_window.tabWidget.count())]
        tab_count = len(tabs)
        source_counts = Counter(os.path.splitext(os.path.basename(tab.property('file_path') or ''))[0].casefold()
                                for tab in tabs)
        if tab_count == 0:
            QtWidgets.QMessageBox.warning(self.main_window, "Batch Export", "No image tabs open. Please open some images first.")
            return
            
        # 让用户选择导出目录
        export_dir = QtWidgets.QFileDialog.getExistingDirectory(
            self.main_window, "Select Export Directory", "",
            QtWidgets.QFileDialog.ShowDirsOnly | QtWidgets.QFileDialog.DontResolveSymlinks
        )
        
        if not export_dir:
            return

        # 创建导出子目录
        rotated_rect_dir = os.path.join(export_dir, "StomataQuant Exported Rotated Rectangle Annotations")
        os.makedirs(rotated_rect_dir, exist_ok=True)
        
        # 创建进度对话框
        progress_dialog = QtWidgets.QProgressDialog("Exporting rotated rectangle annotations...", "Cancel", 0, tab_count, self.main_window)
        progress_dialog.setWindowTitle("Batch Export Progress")
        progress_dialog.setWindowModality(QtCore.Qt.WindowModal)
        progress_dialog.setMinimumDuration(0)
        progress_dialog.setValue(0)
        self.main_window._annotation_batch.progress = progress_dialog
        
        # 保存当前标签页索引
        current_tab_index = self.main_window.tabWidget.currentIndex()
        
        # 统计信息
        exported_count = 0
        skipped_count = 0
        failures = []
        
        try:
            for tab_index in range(tab_count):
                # 检查用户是否取消
                if progress_dialog.wasCanceled():
                    break
                    
                # 设置进度
                progress_dialog.setValue(tab_index)
                progress_dialog.setLabelText(f"Exporting tab {tab_index + 1}/{tab_count}...")
                
                # 切换到当前标签页
                # The target is bound directly; do not activate its GUI.
                QtWidgets.QApplication.processEvents()  # 确保UI更新
                
                # 获取当前标签页信息
                tab = tabs[tab_index]
                if sip.isdeleted(tab) or self.main_window.tabWidget.indexOf(tab) < 0:
                    skipped_count += 1
                    continue
                file_path = tab.property("file_path")
                file_name = os.path.basename(file_path) if file_path else f"tab_{tab_index + 1}"
                
                # 获取当前标签页的图形视图和画布
                graphics_view = tab.property("graphics_view")
                if not graphics_view or not graphics_view.canvas:
                    skipped_count += 1
                    continue
                    
                canvas = graphics_view.canvas
                shapes = canvas.shapes
                
                # 检查是否有旋转矩形形状
                rotated_rect_shapes = [s for s in shapes if s.shape_type == "rotated_rectangle"and s.visible]
                
                if not rotated_rect_shapes:
                    skipped_count += 1
                    continue
                    
                # 生成导出文件名
                # export_filename = os.path.splitext(file_name)[0] + "_rotated_rectangle.txt"
                export_filename = f"Rotated_Rectangle_Annotation_Batch_Exported_by_StomataQuant_{os.path.splitext(file_name)[0]}.txt"
                if file_path and source_counts[os.path.splitext(file_name)[0].casefold()] > 1:
                    export_filename = export_filename[:-4] + '__' + source_suffix(file_path) + '.txt'
                
                # 导出旋转矩形
                try:
                    with io.StringIO() as f:
                        image_width = canvas.image_size.width()
                        image_height = canvas.image_size.height()
                        
                        for shape_index, shape in enumerate(rotated_rect_shapes):
                            if shape_index % 256 == 0:
                                checkpoint(self.main_window, tab, canvas)
                            if len(shape.pointslist) == 4:
                                # 写入YOLO OBB格式: <class> <x1> <y1> <x2> <y2> <x3> <y3> <x4> <y4>
                                points_str = ""
                                for point in shape.pointslist:
                                    # 归一化坐标
                                    norm_x = point.x() / image_width
                                    norm_y = point.y() / image_height
                                    points_str += f" {norm_x:.17g} {norm_y:.17g}"
                                    
                                # 写入YOLO OBB格式的行
                                f.write(f"{shape.classnum}{points_str}\n")
                                
                        content = f.getvalue()
                        validate_rectangle_export(rotated_rect_shapes, content, 'rotated_rectangle',
                                                  image_width, image_height, export_filename)
                    checkpoint(self.main_window, tab, canvas)
                    write_unique_text_atomic(rotated_rect_dir, export_filename, file_path, content)
                    exported_count += 1
                except OperationCancelled:
                    raise
                except Exception as e:
                    print(f"Error exporting rotated rectangles from tab {tab_index + 1}: {str(e)}")
                    failures.append(f"Tab {tab_index + 1} ({file_name}): {e}")
                
                # 更新进度
                progress_dialog.setValue(tab_index + 1)
                QtWidgets.QApplication.processEvents()  # 确保UI更新
                
            # 恢复到原来的标签页
            # Original target restoration is handled by the batch session.
            
            # 关闭进度对话框
            progress_dialog.close()
            
            # 显示结果消息
            if exported_count > 0:
                QtWidgets.QMessageBox.information(
                    self.main_window,
                    "Export Complete",
                    f"Successfully exported rotated rectangle annotations from {exported_count} tabs.\n"
                    f"Skipped {skipped_count} tabs (no rotated rectangle shapes or unavailable).\n"
                    f"Failed to export {len(failures)} tabs.\n" + '\n'.join(failures) + "\n\n"
                    f"Files saved to: {rotated_rect_dir}"
                )
            else:
                QtWidgets.QMessageBox.warning(
                    self.main_window,
                    "Export Complete",
                    f"No rotated rectangle annotations were exported.\n"
                    f"{skipped_count} tabs have no rotated rectangle shapes or are unavailable.\n"
                    f"Failed to export {len(failures)} tabs.\n" + '\n'.join(failures)
                )
                
        except OperationCancelled:
            raise
        except Exception as e:
            progress_dialog.close()
            QtWidgets.QMessageBox.critical(
                self.main_window,
                "Export Error",
                f"An error occurred during batch export: {str(e)}"
            )

# 在现有代码的最后添加

class BatchImporter:
    def import_points(self):
        """Import Point annotations and images using the existing directory workflow."""
        return batch_import_points(self.main_window, self._open_image)

    """
    Batch importer for annotations and corresponding images.
    Supports importing polygons, rectangles, and rotated rectangles.
    """
    def __init__(self, main_window):
        """
        Initialize batch importer
        Args:
            main_window: UIMainWindow instance providing access to main window functionality
        """
        self.main_window = main_window
        
    @annotation_batch(importing=True)
    def import_polygons(self):
        from annotation_matching import run_import
        return run_import(self, 'polygon')

    @annotation_batch(importing=True)
    def import_rectangles(self):
        from annotation_matching import run_import
        return run_import(self, 'rectangle')

    @annotation_batch(importing=True)
    def import_rotated_rectangles(self):
        from annotation_matching import run_import
        return run_import(self, 'rotated_rectangle')


    def _open_image(self, file_path):
        """
        Open an image file and return its tab index
        Returns -1 if opening failed
        
        Args:
            file_path: Path to the image file
            
        Returns:
            int: Tab index where the image was opened, or -1 if failed
        """
        try:
            # Check if the file is already open
            for i in range(self.main_window.tabWidget.count()):
                tab = self.main_window.tabWidget.widget(i)
                if image_path_key(tab.property("file_path")) == image_path_key(file_path):
                    # Already open, return the index
                    return i
            
            # Create new tab
            tab = QWidget()
            tab.setProperty("file_path", file_path)
            
            # Create ImageGraphicsView
            graphics_view = ImageGraphicsView(tab)
            loaded, error = graphics_view.load_image(file_path)
            if not loaded:
                tab.deleteLater()
                return -1
            
            # Set properties
            tab.setProperty("graphics_view", graphics_view)
            
            # Place ImageGraphicsView in tab layout
            layout = QVBoxLayout()
            layout.setContentsMargins(0, 0, 0, 0)
            layout.addWidget(graphics_view)
            tab.setLayout(layout)
            
            # Add to tab widget
            tab_index = self.main_window.tabWidget.addTab(tab, os.path.basename(file_path))
            
            # Connect signals
            graphics_view.zoomChanged.connect(self.main_window.handle_zoom_changed)
            graphics_view.mousePositionChanged.connect(self.main_window.update_mouse_position)
            graphics_view.pixelValueChanged.connect(self.main_window.update_pixel_value)
            
            # Connect canvas signals
            if graphics_view.canvas:
                graphics_view.canvas.shapeSelected.connect(self.main_window.on_shape_selected_in_canvas)
                graphics_view.canvas.shapeCreated.connect(self.main_window.on_shape_created)
                graphics_view.canvas.shapesChanged.connect(self.main_window.on_shapes_changed_in_canvas)
            
            # Switch to new tab
            session = getattr(self.main_window, '_annotation_batch', None)
            if session:
                session.last_new_tab = tab
                session.track(graphics_view.canvas)
            else:
                self.main_window.tabWidget.setCurrentIndex(tab_index)

                        # 添加以下代码修复缩放问题
            # ------ 新增代码开始 ------
            # 调用fit_to_view来适应视图大小
            graphics_view.fit_to_view_custom()
            
            # 更新缩放信息显示
            if not session:
                self.main_window.update_zoom_on_tab_change(tab_index)
            # ------ 新增代码结束 ------
            QtWidgets.QApplication.processEvents()  # Ensure UI updates
            
            return tab_index
        except Exception as e:
            print(f"Error opening image: {e}")
            return -1
    
    def _import_polygon_annotation(self, tab_index, annotation_path, replace=False):
        return self._import_annotation(tab_index, annotation_path, 'polygon', replace)

    def _import_rectangle_annotation(self, tab_index, annotation_path, replace=False):
        return self._import_annotation(tab_index, annotation_path, 'rectangle', replace)

    def _import_rotated_rectangle_annotation(self, tab_index, annotation_path, replace=False):
        return self._import_annotation(tab_index, annotation_path, 'rotated_rectangle', replace)

    def _import_annotation(self, tab_index, annotation_path, kind, replace=False):
        from annotation_io import parse_import_lines, require_annotation_text
        from point_annotations import commit_import
        self.last_import_error = None
        self.last_import_skipped = []
        try:
            tab = self.main_window.tabWidget.widget(tab_index)
            canvas = require_target(self.main_window, tab)
            original = list(canvas.shapes)
            with open(annotation_path, encoding='utf-8-sig') as stream:
                lines = stream.readlines()
            require_annotation_text(lines)
            width, height = canvas.image_size.width(), canvas.image_size.height()
            check = lambda: checkpoint(self.main_window, tab, canvas)
            valid, skipped = parse_import_lines(lines, kind, width, height, check,
                                                with_labels=True)
            next_ids, pending = {}, []
            for number, category, points, label in valid:
                if number % 256 == 1:
                    check()
                if category not in next_ids:
                    ids = [shape.group_id for shape in ([] if replace else original) if shape.classnum == category]
                    next_ids[category] = max(ids) + 1 if ids else 0
                pending.append(Shape(label=label if label is not None else f'class_{category}',
                                     classnum=category, pointslist=points,
                                     shape_type=kind, group_id=next_ids[category], scale_factor=canvas.scale_factor))
                next_ids[category] += 1
            check()
            require_target(self.main_window, tab, canvas)
            commit_import(canvas, pending, replace=replace, expected=original)
            self.last_import_count = len(pending)
            self.last_import_skipped = skipped
            if not getattr(self.main_window, '_defer_batch_refresh', False):
                self.main_window.update_shapes_and_label_list()
            return True
        except OperationCancelled:
            raise
        except Exception as error:
            self.last_import_error = str(error)
            return False
