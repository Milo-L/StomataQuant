import os
import json
from PyQt5.QtCore import QEventLoop, QTimer, Qt
from PyQt5.QtGui import QPixmap, QImageReader
from PyQt5 import QtCore, QtWidgets
from collections import defaultdict
from PyQt5.QtWidgets import QApplication, QDialog, QMessageBox, QWidget, QVBoxLayout
from PyQt5.QtCore import QPointF
import glob
from AllDialogs import BatchProcessingDialog, BatchProgressDialog
from InferenceThread import YOLOSegInferenceThread, HeatMapGenerationThread,PolygonProcessThread
from shape import Shape
from ImageGraphicsView import ImageGraphicsView
from canvas import process_polygon_data
import traceback

class BatchProcessor:
    def __init__(self, main_window):
        """
        初始化批处理器
        Args:
            main_window: UIMainWindow的实例，提供对主窗口功能的访问
        """
        self.main_window = main_window
        
# 在 BatchProcessor 类的 process 方法中添加新选项的处理

    def process(self):
        """
        执行批处理操作
        """
        # 获取所有打开的标签页
        tab_count = self.main_window.tabWidget.count()
        if tab_count == 0:
            QMessageBox.warning(self.main_window, "Batch Processing", "No image tabs open. Please open some images first.")
            return
        
        # 显示批处理选项对话框
        dialog = BatchProcessingDialog(self.main_window)
        if dialog.exec_() != QDialog.Accepted:
            return
        
        options = dialog.get_options()
        # 保存选项供其他方法使用
        self.batch_options = options
        

        # 修改后的代码 - 无论设置值如何都执行
        has_group_id_operation = "group_id_display" in options  # 只要有这个选项就执行
        has_class_visibility_operation = "class_visibility" in options  # 只要有这个选项就执行
        
        # 如果没有选择任何操作，则返回
        if not any([
            options["ai"], 
            options["filter"], 
            options["show_points"], 
            options["mer"], 
            options["feature_extraction"], 
            options["heatmap"],
            has_group_id_operation,  # 添加group_id显示检查
            has_class_visibility_operation  # 添加class_visibility检查
        ]):
            QMessageBox.information(self.main_window, "Batch Processing", "No operations selected.")
            return
        
        # 保存热图设置以供后续使用
        if options["heatmap"] and "heatmap_settings" in options:
            self.batch_heatmap_settings = options["heatmap_settings"]
        
        # 计算总操作数
        operations_per_tab = sum([
            1 if options["ai"] else 0,
            1 if options["filter"] else 0,
            1 if options["show_points"] else 0,
            1 if options["mer"] else 0,
            1 if options["feature_extraction"] else 0,
            1 if options["heatmap"] else 0,
            1 if has_group_id_operation else 0,  # 添加group_id显示为独立操作
            1 if has_class_visibility_operation else 0  # 添加class_visibility为独立操作
        ])
        
        total_operations = tab_count * operations_per_tab
        
        if total_operations == 0:
            QMessageBox.information(self.main_window, "Batch Processing", "No operations to perform.")
            return
        
        # 创建进度对话框
        progress_dialog = BatchProgressDialog(self.main_window)
        progress_dialog.set_max_operations(total_operations)
        progress_dialog.show()
        
        # 保存当前标签页索引
        current_tab_index = self.main_window.tabWidget.currentIndex()
        
        # 用于跟踪成功和失败的操作
        results = {
            "success": 0,
            "failed": 0,
            "skipped": 0,
            "operations": {
                "ai": {"success": 0, "failed": 0},
                "filter": {"success": 0, "failed": 0},
                "show_points": {"success": 0, "failed": 0},
                "mer": {"success": 0, "failed": 0},
                "feature_extraction": {"success": 0, "failed": 0},
                "heatmap": {"success": 0, "failed": 0}
            }
        }
        
        # 初始化操作计数器
        operation_count = 0
        
        try:
            for tab_index in range(tab_count):
                # 切换到当前标签页
                self.main_window.tabWidget.setCurrentIndex(tab_index)
                QApplication.processEvents()  # 确保UI更新
                
                tab = self.main_window.tabWidget.widget(tab_index)
                file_path = tab.property("file_path")
                progress_dialog.set_tab_info(tab_index + 1, tab_count)
                
                file_name = os.path.basename(file_path) if file_path else "Unknown"
                progress_dialog.update_file(file_name)
                
                # 获取当前标签页的 GraphicsView 和 Canvas
                graphics_view = tab.property("graphics_view")
                
                if not graphics_view or not graphics_view.canvas:
                    progress_dialog.update_status(f"Skipping tab {tab_index + 1}: Canvas not initialized")
                    results["skipped"] += 1
                    continue
                
                # 执行AI推理
                if options["ai"]:
                    self._process_ai_operation(tab_index, file_path, graphics_view, progress_dialog, results)
                    operation_count += 1
                    progress_dialog.update_overall_progress(operation_count)
                
                # 执行过滤操作
                if options["filter"]:
                    self._process_filter_operation(tab_index, graphics_view, options["filter"], progress_dialog, results)
                    operation_count += 1
                    progress_dialog.update_overall_progress(operation_count)

                if has_group_id_operation:
                    self._process_group_id_display(tab_index, graphics_view, options["group_id_display"], progress_dialog)
                    operation_count += 1
                    progress_dialog.update_overall_progress(operation_count)
                
                # 添加独立的类别可见性处理
                if has_class_visibility_operation:
                    self._process_class_visibility(tab_index, graphics_view, options["class_visibility"], progress_dialog)
                    operation_count += 1
                    progress_dialog.update_overall_progress(operation_count)

                # 执行显示点操作
                if options["show_points"]:
                    self._process_show_points_operation(tab_index, graphics_view, progress_dialog, results)
                    operation_count += 1
                    progress_dialog.update_overall_progress(operation_count)
                
                # 执行MER操作
                if options["mer"]:
                    self._process_mer_operation(tab_index, graphics_view, progress_dialog, results)
                    operation_count += 1
                    progress_dialog.update_overall_progress(operation_count)
                
                # 执行特征提取
                if options["feature_extraction"]:
                    self._process_feature_extraction(tab_index, graphics_view, progress_dialog, results)
                    operation_count += 1
                    progress_dialog.update_overall_progress(operation_count)
                
                # 执行热图生成
                if options["heatmap"]:
                    self._process_heatmap_operation(tab_index, graphics_view, progress_dialog, results)
                    operation_count += 1
                    progress_dialog.update_overall_progress(operation_count)
                
                # 检查用户是否取消
                if progress_dialog.canceled:
                    progress_dialog.update_status("Processing canceled by user")
                    break
                
                # 完成了一个标签页的所有操作
                results["success"] += 1
        
        except Exception as e:
            QMessageBox.critical(self.main_window, "Error", f"An unexpected error occurred during batch processing: {str(e)}")
        
        # 在finally块中，修改现有循环
        finally:
            # 添加循环，强制更新所有处理过的标签页
            for tab_index in range(tab_count):
                try:
                    self.main_window.tabWidget.setCurrentIndex(tab_index)
                    QApplication.processEvents()  # 确保UI更新
                    graphics_view = self.main_window.get_current_graphics_view()
                    graphics_view.fit_to_view_custom()
     
                except Exception as e:
                    print(f"Error updating tab {tab_index}: {str(e)}")
                    
            # 恢复到原来的标签页
            self.main_window.tabWidget.setCurrentIndex(current_tab_index)
            graphics_view = self.main_window.get_current_graphics_view()
            if graphics_view and graphics_view.canvas:
                graphics_view.canvas.set_mode('edit')
                self.main_window.actionEditShapes.setChecked(True)
                
                # 使用UIMainWindow的完整更新方法
                self.main_window.update_shapes_and_label_list()
                self.main_window.labeldockinstance.populate(graphics_view.canvas.shapes, Shape.get_color_by_classnum)
                self.main_window.shapedockinstance.populate(graphics_view.canvas.shapes)
                self.main_window.get_current_graphics_view().canvas.update()
                self.main_window.edit_shapes()  # 这会处理编辑模式下的各种按钮状态
            
            # 关闭进度对话框
            # 在处理完成后允许关闭
            progress_dialog.allow_close()
            progress_dialog.close()
            
            # 显示结果摘要
            self._display_results_summary(tab_count, results, options)

    def _process_class_visibility(self, tab_index, graphics_view, class_visibility, progress_dialog):
        """处理类别可见性设置"""
        try:
            progress_dialog.update_operation("Applying class visibility settings")
            progress_dialog.update_operation_progress(0)
            
            canvas = graphics_view.canvas
            shapes = canvas.shapes
            
            # 应用类别可见性设置
            visibility_changed = False
            for i, shape in enumerate(shapes):
                if hasattr(shape, 'classnum') and shape.classnum in class_visibility:
                    old_visibility = shape.visible
                    shape.visible = class_visibility[shape.classnum]
                    if old_visibility != shape.visible:
                        visibility_changed = True
                        shape._dirty = True  # 标记为脏以确保重绘
                
                # 更新进度
                progress_dialog.update_operation_progress(int((i+1) * 100 / len(shapes)))
            
            if visibility_changed:
                # 更新画布
                canvas.update()
                canvas.shapesChanged.emit()
                
                # 记录操作状态到进度对话框
                progress_dialog.update_status(f"Tab {tab_index + 1}: Applied class visibility settings")
            
            progress_dialog.update_operation_progress(100)
            
        except Exception as e:
            progress_dialog.update_status(f"Error setting class visibility in tab {tab_index + 1}: {str(e)}")
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
            canvas.update()
            canvas.shapesChanged.emit()
            
            # 记录操作状态到进度对话框
            progress_dialog.update_status(f"Tab {tab_index + 1}: Group ID display set to '{display_option}'")
            
        except Exception as e:
            progress_dialog.update_status(f"Error setting group ID display in tab {tab_index + 1}: {str(e)}")
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
                    canvas.update()
                    canvas.shapesChanged.emit()
                    
                progress_dialog.update_operation_progress(100)
                results["operations"]["show_points"]["success"] += 1
            else:
                progress_dialog.update_status(f"No visible shapes in tab {tab_index + 1}")
                results["operations"]["show_points"]["skipped"] = results["operations"]["show_points"].get("skipped", 0) + 1
        
        except Exception as e:
            progress_dialog.update_status(f"Error in tab {tab_index + 1} show points operation: {str(e)}")
            results["operations"]["show_points"]["failed"] += 1
        
    def _process_ai_operation(self, tab_index, file_path, graphics_view, progress_dialog, results):
        """处理AI推理操作"""
        try:
            progress_dialog.update_operation("Running YOLO Inference")
            progress_dialog.update_operation_progress(0)
            
            # 检查是否有模型
            if not hasattr(self.main_window, 'model') or not self.main_window.model:
                progress_dialog.update_status("Error: No model loaded")
                results["operations"]["ai"]["failed"] += 1
                return
            
            # 准备推理参数
            inference_settings = self.main_window.inference_settings.copy() if hasattr(self.main_window, 'inference_settings') and self.main_window.inference_settings else {
                "conf": 0.5,
                "iou": 0.7,
                "device": "cpu",
                "save_path": os.path.join(os.getcwd(), "Inference_OutPut"),
                "imgsz": 1024,
                "max_det": 500
            }
            
            # 创建批处理版本的推理线程
            batch_thread = YOLOSegInferenceThread(self.main_window.model, file_path, inference_settings, self.main_window)
            
            # 创建一个事件循环来等待线程完成
            loop = QEventLoop()
            
            # 保存引用，让批处理结束时可以使用
            batch_results = {"results": None, "error": None}
            
            def on_batch_inference_finished(results, file_path, error):
                batch_results["results"] = results
                batch_results["error"] = error
                loop.quit()
            
            batch_thread.inferenceFinished.connect(on_batch_inference_finished)
            
            # 启动线程
            batch_thread.start()
            
            # 进度更新
            progress_timer = QTimer()
            progress_value = 0
            
            def update_progress():
                nonlocal progress_value
                progress_value = min(99, progress_value + 5)  # 模拟进度，最多到99%
                progress_dialog.update_operation_progress(progress_value)
                
            progress_timer.timeout.connect(update_progress)
            progress_timer.start(500)  # 每0.5秒更新一次
            
            # 等待线程完成
            loop.exec_()
            progress_timer.stop()
            
            # 检查是否有错误
            if batch_results["error"]:
                progress_dialog.update_status(f"Error in tab {tab_index + 1}: {batch_results['error']}")
                results["operations"]["ai"]["failed"] += 1
                
            else:
                # 手动处理结果
                self._process_yolo_results(batch_results["results"], file_path, graphics_view.canvas)
                progress_dialog.update_operation_progress(100)
                results["operations"]["ai"]["success"] += 1
        
        except Exception as e:
            progress_dialog.update_status(f"Error in tab {tab_index + 1} AI operation: {str(e)}")
            results["operations"]["ai"]["failed"] += 1
    
    def _process_filter_operation(self, tab_index, graphics_view, filter_type, progress_dialog, results):
        """处理过滤操作"""
        try:
            if filter_type:
                progress_dialog.update_operation(f"Applying filter: {filter_type}")
                progress_dialog.update_operation_progress(0)
                
                canvas = graphics_view.canvas
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
        """处理MER操作"""
        try:
            progress_dialog.update_operation("Calculating Minimum Enclosing Rectangle")
            progress_dialog.update_operation_progress(0)
            
            canvas = graphics_view.canvas
            polygon_shapes = [s for s in canvas.shapes if s.visible and s.shape_type == "polygon"]
            
            if polygon_shapes:
                # 保存初始状态用于撤销
                canvas.save_state()
                
                # 存储临时选中状态
                temp_selected = canvas.selected_shape.copy() if canvas.selected_shape else []
                canvas.selected_shape = []
                
                # 添加MER形状
                new_shapes = []
                for i, shape in enumerate(polygon_shapes):
                    progress_dialog.update_operation_progress(int((i+1) * 100 / len(polygon_shapes)))
                    rotated_rect_shape = shape.calculate_minimum_rotated_rectangle()
                    if rotated_rect_shape:
                        new_shapes.append(rotated_rect_shape)
                
                # 添加新形状到画布
                canvas.shapes.extend(new_shapes)
                
                # 新增代码：如果选择了隐藏原始多边形，则设置所有多边形为不可见
                if self.batch_options.get("hide_original_polygons", False):
                    for shape in polygon_shapes:
                        shape.visible = False
                    progress_dialog.update_status(f"Tab {tab_index + 1}: Original polygons hidden")
                
                # 恢复选中状态
                canvas.selected_shape = temp_selected
                canvas.update()
                
                progress_dialog.update_operation_progress(100)
                results["operations"]["mer"]["success"] += 1
            else:
                progress_dialog.update_status(f"No polygon shapes in tab {tab_index + 1}")
                results["operations"]["mer"]["skipped"] = results["operations"]["mer"].get("skipped", 0) + 1
        
        except Exception as e:
            progress_dialog.update_status(f"Error in tab {tab_index + 1} MER operation: {str(e)}")
            results["operations"]["mer"]["failed"] += 1
    
    def _process_feature_extraction(self, tab_index, graphics_view, progress_dialog, results):
        """处理特征提取操作"""
        try:
            progress_dialog.update_operation("Extracting features")
            progress_dialog.update_operation_progress(0)
            
            canvas = graphics_view.canvas
            visible_shapes = [s for s in canvas.shapes if s.visible]
            
            if visible_shapes:
                # 获取图像尺寸（用于结果汇总）
                image_size = canvas.image_size
                image_width = image_size.width()
                image_height = image_size.height()
                
                # 获取比例尺信息 - 全局优先
                scale_info = None
                # 检查是否使用全局比例尺
                if hasattr(self.main_window, 'global_scale_info') and self.main_window.global_scale_info:
                    scale_info = self.main_window.global_scale_info
                    progress_dialog.update_status(f"Tab {tab_index + 1}: Using global scale ({scale_info['scale']} {scale_info['unit']})")
                # 否则尝试使用当前视图的比例尺
                elif hasattr(graphics_view, 'scale_info') and graphics_view.scale_info:
                    scale_info = graphics_view.scale_info
                    progress_dialog.update_status(f"Tab {tab_index + 1}: Using local scale ({scale_info['scale']} {scale_info['unit']})")
                else:
                    progress_dialog.update_status(f"Tab {tab_index + 1}: No scale information available. Using pixel units.")
                
                # 执行特征提取
                for i, s in enumerate(visible_shapes):
                    progress_dialog.update_operation_progress(int((i+1) * 100 / len(visible_shapes)))
                    if s.shape_type == "polygon":
                        s.feature_extraction_polygon(scale_info=scale_info)
                    elif s.shape_type == "rectangle":
                        s.feature_extraction_rectangle(scale_info=scale_info)
                    elif s.shape_type == "rotated_rectangle":
                        s.feature_extraction_rotated_rectangle(scale_info=scale_info)
                    elif s.shape_type == "line":
                        s.feature_extraction_line(scale_info=scale_info)
                    elif s.shape_type == "point":
                        s.feature_extraction_point(scale_info=scale_info)
                
                progress_dialog.update_operation_progress(100)
                results["operations"]["feature_extraction"]["success"] += 1
                
                # 更新当前标签页的结果显示（如果处理的是当前显示的标签页）
                if tab_index == self.main_window.tabWidget.currentIndex():
                    self.main_window.measured_results_dock.populate(visible_shapes)
                    self.main_window.image_results_summary_dock.populate(
                        visible_shapes, image_width, image_height, scale_info
                    )
            else:
                progress_dialog.update_status(f"No visible shapes in tab {tab_index + 1}")
                results["operations"]["feature_extraction"]["skipped"] = results["operations"]["feature_extraction"].get("skipped", 0) + 1
        
        except Exception as e:
            progress_dialog.update_status(f"Error in tab {tab_index + 1} feature extraction: {str(e)}")
            results["operations"]["feature_extraction"]["failed"] += 1

    
    def _process_heatmap_operation(self, tab_index, graphics_view, progress_dialog, results):
        """处理热图操作"""
        try:
            progress_dialog.update_operation("正在生成热图")
            progress_dialog.update_operation_progress(0)
            
            # 获取当前可见的多边形形状
            canvas = graphics_view.canvas
            shapes = [s for s in canvas.shapes if s.visible and s.shape_type == 'polygon']
            
            # 获取当前标签页和文件信息
            tab = self.main_window.tabWidget.widget(tab_index)
            file_path = tab.property("file_path") if tab else None
            file_name = os.path.basename(file_path) if file_path else f"tab_{tab_index + 1}"
            
            if shapes and any(hasattr(s, 'feature_results') and s.feature_results for s in shapes):
                # 使用预设的热图设置
                heatmap_settings = getattr(self.main_window, 'heatmap_settings', {})
                # 使用从对话框获取的批处理热图设置
                if hasattr(self, 'batch_heatmap_settings') and self.batch_heatmap_settings:
                    heatmap_settings = self.batch_heatmap_settings
                    
                feature_name = heatmap_settings.get("feature", "Area")  # 默认特征
                colormap_name = heatmap_settings.get("colormap", "viridis")  # 默认颜色图
                
                # 获取比例尺信息 - 与单个图像处理保持一致
                scale_info = None
                # 检查特征是否需要比例尺
                needs_scale = feature_name in ["Area", "Perimeter", "MER Length", "MER Width"]
                
                # 如果需要比例尺，则尝试获取
                if needs_scale:
                    # 优先使用全局比例尺
                    if hasattr(self.main_window, 'global_scale_info') and self.main_window.global_scale_info:
                        scale_info = self.main_window.global_scale_info
                        progress_dialog.update_status(f"Tab {tab_index + 1}: Using global scale for heatmap")
                    # 否则尝试使用当前视图的比例尺
                    elif hasattr(graphics_view, 'scale_info') and graphics_view.scale_info:
                        scale_info = graphics_view.scale_info
                        progress_dialog.update_status(f"Tab {tab_index + 1}: Using local scale for heatmap")
                    else:
                        progress_dialog.update_status(f"Tab {tab_index + 1}: Warning - {feature_name} requires scale but no scale information is available")
                
                # 设置输出路径
                output_path = heatmap_settings.get("output_path", os.path.join(os.getcwd(), "Heatmaps"))
                os.makedirs(output_path, exist_ok=True)
                
                # 获取图像
                original_pixmap = graphics_view.pixmap_item.pixmap()
                original_image = original_pixmap.toImage()
                
                # 创建并等待热图线程
                loop = QEventLoop()
                heatmap_result = {"path": "", "error": None}
                
                def on_heatmap_generated(file_path, error):
                    heatmap_result["path"] = file_path
                    heatmap_result["error"] = error
                    loop.quit()
                
                # 创建热图线程 - 加入文件名和比例尺信息
                heatmap_thread = HeatMapGenerationThread(
                    original_image,
                    shapes,
                    feature_name,
                    colormap_name,
                    output_path,
                    file_path,  # 传递原始文件路径用于命名
                    scale_info,  # 传递比例尺信息
                    self.main_window
                )
                heatmap_thread.heatmapGenerated.connect(on_heatmap_generated)
                
                # 启动线程
                heatmap_thread.start()
                
                # 进度更新
                progress_timer = QTimer()
                progress_value = 0
                
                def update_progress():
                    nonlocal progress_value
                    progress_value = min(99, progress_value + 5)
                    progress_dialog.update_operation_progress(progress_value)
                    
                progress_timer.timeout.connect(update_progress)
                progress_timer.start(500)
                
                # 等待线程完成
                loop.exec_()
                progress_timer.stop()
                
                if heatmap_result["error"]:
                    progress_dialog.update_status(f"标签页 {tab_index + 1} 生成热图时出错: {heatmap_result['error']}")
                    results["operations"]["heatmap"]["failed"] += 1
                else:
                    progress_dialog.update_operation_progress(100)
                    progress_dialog.update_status(f"标签页 {tab_index + 1}: 热图已保存至: {heatmap_result['path']}")
                    results["operations"]["heatmap"]["success"] += 1
            else:
                if not shapes:
                    progress_dialog.update_status(f"标签页 {tab_index + 1} 中没有多边形形状")
                else:
                    progress_dialog.update_status(f"标签页 {tab_index + 1} 中没有可用的特征数据")
                results["operations"]["heatmap"]["skipped"] = results["operations"]["heatmap"].get("skipped", 0) + 1
        
        except Exception as e:
            progress_dialog.update_status(f"标签页 {tab_index + 1} 热图生成出错: {str(e)}")
            results["operations"]["heatmap"]["failed"] += 1
    
# 修改_process_yolo_results方法

    def _process_yolo_results(self, results, file_path, canvas):
        """处理YOLO推理结果并将其添加到指定的Canvas上，包含与主文件一致的处理逻辑"""
        try:
            # 创建用于存储box类型形状的列表
            box_shapes = []
            # 检查结果是否有效
            if not results:
                return []
            
            # 处理输出目录
            output_dir = self.main_window.inference_settings.get("save_path", os.path.join(os.getcwd(), "Inference_OutPut")) if hasattr(self.main_window, 'inference_settings') else os.path.join(os.getcwd(), "Inference_OutPut")
            os.makedirs(output_dir, exist_ok=True)
            
            # 标记是否有segments类型的数据
            has_segments = False
            
            # 处理每个结果
            for result in results:
                json_str = result.to_json()
                json_obj = json.loads(json_str)
                
                # 生成并保存JSON文件
                json_file_path = os.path.join(output_dir, f"{os.path.splitext(os.path.basename(result.path))[0]}.json")
                
                with open(json_file_path, 'w') as json_file:
                    json.dump(json_obj, json_file, indent=4)
                
                # 处理JSON对象中的形状数据
                if isinstance(json_obj, list):
                    image_size = canvas.image_size
                    image_width = image_size.width()
                    image_height = image_size.height()
                    
                    # 处理类别计数，与主文件保持一致
                    class_counts = defaultdict(int)
                    
                    # 直接处理box类型的项目
                    for item in json_obj:
                        # 仅处理box类型
                        if 'segments' not in item and 'box' in item:
                            box = item['box']
                            x1, y1 = box.get('x1', 0), box.get('y1', 0)
                            x2, y2 = box.get('x2', 0), box.get('y2', 0)
                            top_left = QPointF(x1, y1)
                            bottom_right = QPointF(x2, y2)
                            label = item.get('name', 'undefined')
                            classnum = item.get('class', 'undefined')
                            
                            # 分配group_id与主文件保持一致
                            group_id = class_counts[classnum]
                            class_counts[classnum] += 1
                            
                            # 创建矩形形状
                            shape = Shape(
                                label=label, 
                                classnum=classnum,
                                pointslist=[top_left, bottom_right], 
                                shape_type='rectangle', 
                                group_id=group_id,
                                scale_factor=canvas.scale_factor
                            )
                            box_shapes.append(shape)
                        
                        # 检查是否有多边形(segments)数据
                        elif 'segments' in item:
                            has_segments = True
                            
                    # 如果存在segments类型数据，在批处理中我们直接处理它们
                    # 因为在批处理中启动新线程并等待可能会造成UI阻塞
                    if has_segments:
                        # 收集所有具有segments的项
                        segment_items = [item for item in json_obj if 'segments' in item]
                        if segment_items:
                            # 按classnum分组收集坐标
                            polygons_by_class = {}
                            for item in segment_items:
                                x_coords = item['segments'].get('x', [])
                                y_coords = item['segments'].get('y', [])
                                if len(x_coords) != len(y_coords):
                                    continue
                                    
                                classnum = item.get('class', 'undefined')
                                if classnum not in polygons_by_class:
                                    polygons_by_class[classnum] = []
                                
                                polygons_by_class[classnum].append((x_coords, y_coords))
                            
                            # 在批处理中，直接处理多边形数据而不启动新线程
                            if polygons_by_class:
                                # 调用处理函数
                                processed_map = process_polygon_data(
                                    polygons_by_class, image_width, image_height)
                                
                                # 处理结果转换为Shape对象
                                for classnum, polygons in processed_map.items():
                                    for i, (pointsx, pointsy) in enumerate(polygons):
                                        points = [QPointF(x, y) for x, y in zip(pointsx, pointsy)]
                                        if len(points) >= 3:
                                            # 创建多边形形状
                                            shape = Shape(
                                                label=f"class_{classnum}",
                                                classnum=classnum,
                                                pointslist=points,
                                                shape_type='polygon',
                                                group_id=i,
                                                scale_factor=canvas.scale_factor
                                            )
                                            box_shapes.append(shape)
            
            # 将形状添加到画布
            canvas.shapes.extend(box_shapes)
            canvas.update()
            
            # 更新UI - 使用主窗口中已定义的更完整方法
            self.main_window.labeldockinstance.populate(canvas.shapes, Shape.get_color_by_classnum)
            self.main_window.shapedockinstance.populate(canvas.shapes)
            
            # 设置为编辑模式
            canvas.set_mode('edit')
            
            return box_shapes
                
        except Exception as e:
            print(f"Error processing YOLO results: {str(e)}")
            print(traceback.format_exc())
            return []

    def _display_results_summary(self, tab_count, results, options):
        """显示批处理结果摘要"""
        summary = "Batch Processing Results:\n\n"
        summary += f"Total tabs: {tab_count}\n"
        summary += f"Successfully processed: {results['success']}\n"
        summary += f"Failed: {results['failed']}\n"
        summary += f"Skipped: {results['skipped']}\n\n"
        
        if results["operations"]:
            summary += "Operations Summary:\n"
            
            # 添加Group ID显示设置
            summary += f"  - Group ID Display: Set to '{options['group_id_display']}'\n"
            
            # 添加类别可见性设置信息 - 新增代码
            if 'class_visibility' in options and options.get('filter'):
                class_visibility = options['class_visibility']
                summary += "  - Class Visibility Settings:\n"
                summary += f"    - Class 0 (stoma): {'Visible' if class_visibility[0] else 'Hidden'}\n"
                summary += f"    - Class 1 (pore/cell): {'Visible' if class_visibility[1] else 'Hidden'}\n"
            
            for op_name, counts in results["operations"].items():
                if op_name in options and options[op_name]:
                    success = counts.get("success", 0)
                    failed = counts.get("failed", 0)
                    skipped = counts.get("skipped", 0)
                    summary += f"  - {op_name.replace('_', ' ').title()}: {success} success, {failed} failed, {skipped} skipped\n"
        
        QMessageBox.information(self.main_window, "Batch Processing Complete", summary)

# 在现有代码的最后添加

class BatchExporter:
    def __init__(self, main_window):
        """
        初始化批量导出器
        Args:
            main_window: UIMainWindow的实例，提供对主窗口功能的访问
        """
        self.main_window = main_window
        
    def export_polygons(self):
        """批量导出所有标签页中的多边形形状"""
        # 获取所有打开的标签页
        tab_count = self.main_window.tabWidget.count()
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
        
        # 保存当前标签页索引
        current_tab_index = self.main_window.tabWidget.currentIndex()
        
        # 统计信息
        exported_count = 0
        skipped_count = 0
        
        try:
            for tab_index in range(tab_count):
                # 检查用户是否取消
                if progress_dialog.wasCanceled():
                    break
                    
                # 设置进度
                progress_dialog.setValue(tab_index)
                progress_dialog.setLabelText(f"Exporting tab {tab_index + 1}/{tab_count}...")
                
                # 切换到当前标签页
                self.main_window.tabWidget.setCurrentIndex(tab_index)
                QtWidgets.QApplication.processEvents()  # 确保UI更新
                
                # 获取当前标签页信息
                tab = self.main_window.tabWidget.widget(tab_index)
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
                export_path = os.path.join(polygon_dir, export_filename)
                
                # 导出多边形
                try:
                    with open(export_path, 'w') as f:
                        image_width = canvas.image_size.width()
                        image_height = canvas.image_size.height()
                        
                        for shape in polygon_shapes:
                            # YOLO格式: <class> <x1> <y1> <x2> <y2> ... <xn> <yn>
                            points_str = ""
                            for point in shape.pointslist:
                                # 归一化坐标
                                norm_x = point.x() / image_width
                                norm_y = point.y() / image_height
                                points_str += f" {norm_x:.6f} {norm_y:.6f}"
                                
                            # 写入YOLO格式的行
                            f.write(f"{shape.classnum}{points_str}\n")
                            
                    exported_count += 1
                except Exception as e:
                    print(f"Error exporting polygons from tab {tab_index + 1}: {str(e)}")
                    skipped_count += 1
                
                # 更新进度
                progress_dialog.setValue(tab_index + 1)
                QtWidgets.QApplication.processEvents()  # 确保UI更新
                
            # 恢复到原来的标签页
            self.main_window.tabWidget.setCurrentIndex(current_tab_index)
            
            # 关闭进度对话框
            progress_dialog.close()
            
            # 显示结果消息
            if exported_count > 0:
                QtWidgets.QMessageBox.information(
                    self.main_window,
                    "Export Complete",
                    f"Successfully exported polygon annotations from {exported_count} tabs.\n"
                    f"Skipped {skipped_count} tabs (no polygon shapes).\n\n"
                    f"Files saved to: {polygon_dir}"
                )
            else:
                QtWidgets.QMessageBox.warning(
                    self.main_window,
                    "Export Complete",
                    f"No polygon annotations were exported.\n"
                    f"All {skipped_count} tabs have no polygon shapes."
                )
                
        except Exception as e:
            progress_dialog.close()
            QtWidgets.QMessageBox.critical(
                self.main_window,
                "Export Error",
                f"An error occurred during batch export: {str(e)}"
            )
            
    def export_rectangles(self):
        """批量导出所有标签页中的矩形形状"""
        # 获取所有打开的标签页
        tab_count = self.main_window.tabWidget.count()
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
        
        # 保存当前标签页索引
        current_tab_index = self.main_window.tabWidget.currentIndex()
        
        # 统计信息
        exported_count = 0
        skipped_count = 0
        
        try:
            for tab_index in range(tab_count):
                # 检查用户是否取消
                if progress_dialog.wasCanceled():
                    break
                    
                # 设置进度
                progress_dialog.setValue(tab_index)
                progress_dialog.setLabelText(f"Exporting tab {tab_index + 1}/{tab_count}...")
                
                # 切换到当前标签页
                self.main_window.tabWidget.setCurrentIndex(tab_index)
                QtWidgets.QApplication.processEvents()  # 确保UI更新
                
                # 获取当前标签页信息
                tab = self.main_window.tabWidget.widget(tab_index)
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
                export_path = os.path.join(rectangle_dir, export_filename)
                
                # 导出矩形
                try:
                    with open(export_path, 'w') as f:
                        image_width = canvas.image_size.width()
                        image_height = canvas.image_size.height()
                        
                        for shape in rectangle_shapes:
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
                                
                    exported_count += 1
                except Exception as e:
                    print(f"Error exporting rectangles from tab {tab_index + 1}: {str(e)}")
                    skipped_count += 1
                
                # 更新进度
                progress_dialog.setValue(tab_index + 1)
                QtWidgets.QApplication.processEvents()  # 确保UI更新
                
            # 恢复到原来的标签页
            self.main_window.tabWidget.setCurrentIndex(current_tab_index)
            
            # 关闭进度对话框
            progress_dialog.close()
            
            # 显示结果消息
            if exported_count > 0:
                QtWidgets.QMessageBox.information(
                    self.main_window,
                    "Export Complete",
                    f"Successfully exported rectangle annotations from {exported_count} tabs.\n"
                    f"Skipped {skipped_count} tabs (no rectangle shapes).\n\n"
                    f"Files saved to: {rectangle_dir}"
                )
            else:
                QtWidgets.QMessageBox.warning(
                    self.main_window,
                    "Export Complete",
                    f"No rectangle annotations were exported.\n"
                    f"All {skipped_count} tabs have no rectangle shapes."
                )
                
        except Exception as e:
            progress_dialog.close()
            QtWidgets.QMessageBox.critical(
                self.main_window,
                "Export Error",
                f"An error occurred during batch export: {str(e)}"
            )
            
    def export_rotated_rectangles(self):
        """批量导出所有标签页中的旋转矩形形状"""
        # 获取所有打开的标签页
        tab_count = self.main_window.tabWidget.count()
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
        
        # 保存当前标签页索引
        current_tab_index = self.main_window.tabWidget.currentIndex()
        
        # 统计信息
        exported_count = 0
        skipped_count = 0
        
        try:
            for tab_index in range(tab_count):
                # 检查用户是否取消
                if progress_dialog.wasCanceled():
                    break
                    
                # 设置进度
                progress_dialog.setValue(tab_index)
                progress_dialog.setLabelText(f"Exporting tab {tab_index + 1}/{tab_count}...")
                
                # 切换到当前标签页
                self.main_window.tabWidget.setCurrentIndex(tab_index)
                QtWidgets.QApplication.processEvents()  # 确保UI更新
                
                # 获取当前标签页信息
                tab = self.main_window.tabWidget.widget(tab_index)
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
                export_path = os.path.join(rotated_rect_dir, export_filename)
                
                # 导出旋转矩形
                try:
                    with open(export_path, 'w') as f:
                        image_width = canvas.image_size.width()
                        image_height = canvas.image_size.height()
                        
                        for shape in rotated_rect_shapes:
                            if len(shape.pointslist) == 4:
                                # 写入YOLO OBB格式: <class> <x1> <y1> <x2> <y2> <x3> <y3> <x4> <y4>
                                points_str = ""
                                for point in shape.pointslist:
                                    # 归一化坐标
                                    norm_x = point.x() / image_width
                                    norm_y = point.y() / image_height
                                    points_str += f" {norm_x:.6f} {norm_y:.6f}"
                                    
                                # 写入YOLO OBB格式的行
                                f.write(f"{shape.classnum}{points_str}\n")
                                
                    exported_count += 1
                except Exception as e:
                    print(f"Error exporting rotated rectangles from tab {tab_index + 1}: {str(e)}")
                    skipped_count += 1
                
                # 更新进度
                progress_dialog.setValue(tab_index + 1)
                QtWidgets.QApplication.processEvents()  # 确保UI更新
                
            # 恢复到原来的标签页
            self.main_window.tabWidget.setCurrentIndex(current_tab_index)
            
            # 关闭进度对话框
            progress_dialog.close()
            
            # 显示结果消息
            if exported_count > 0:
                QtWidgets.QMessageBox.information(
                    self.main_window,
                    "Export Complete",
                    f"Successfully exported rotated rectangle annotations from {exported_count} tabs.\n"
                    f"Skipped {skipped_count} tabs (no rotated rectangle shapes).\n\n"
                    f"Files saved to: {rotated_rect_dir}"
                )
            else:
                QtWidgets.QMessageBox.warning(
                    self.main_window,
                    "Export Complete",
                    f"No rotated rectangle annotations were exported.\n"
                    f"All {skipped_count} tabs have no rotated rectangle shapes."
                )
                
        except Exception as e:
            progress_dialog.close()
            QtWidgets.QMessageBox.critical(
                self.main_window,
                "Export Error",
                f"An error occurred during batch export: {str(e)}"
            )

# 在现有代码的最后添加

class BatchImporter:
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
        
    def import_polygons(self):
        """Import polygon annotations and corresponding images in batch"""
        # Select image directory
        image_dir = QtWidgets.QFileDialog.getExistingDirectory(
            self.main_window, "Select Image Directory", "",
            QtWidgets.QFileDialog.ShowDirsOnly | QtWidgets.QFileDialog.DontResolveSymlinks
        )
        
        if not image_dir:
            return
            
        # Select annotation directory
        annotation_dir = QtWidgets.QFileDialog.getExistingDirectory(
            self.main_window, "Select Polygon Annotation Directory", "",
            QtWidgets.QFileDialog.ShowDirsOnly | QtWidgets.QFileDialog.DontResolveSymlinks
        )
        
        if not annotation_dir:
            return
            
        # Scan directories for images and annotation files - FIX: avoid duplicates
        image_files = set()  # Use a set to avoid duplicates
        for ext in ['.png', '.jpg', '.jpeg', '.bmp', '.tif']:
            # Find files with both lowercase and uppercase extensions
            found_files = glob.glob(os.path.join(image_dir, f"*{ext}"))
            found_files.extend(glob.glob(os.path.join(image_dir, f"*{ext.upper()}")))
            # Add to set to eliminate duplicates
            image_files.update(found_files)
        
        # Convert back to list
        image_files = list(image_files)
        
        annotation_files = glob.glob(os.path.join(annotation_dir, "*.txt"))
        
        if not image_files:
            QtWidgets.QMessageBox.warning(
                self.main_window,
                "Import Error",
                f"No image files found in the specified directory: {image_dir}"
            )
            return
            
        if not annotation_files:
            QtWidgets.QMessageBox.warning(
                self.main_window,
                "Import Error",
                f"No annotation files found in the specified directory: {annotation_dir}"
            )
            return
        
        # Create progress dialog
        progress_dialog = QtWidgets.QProgressDialog("Importing images and annotations...", "Cancel", 0, len(image_files), self.main_window)
        progress_dialog.setWindowTitle("Batch Import Progress")
        progress_dialog.setWindowModality(QtCore.Qt.WindowModal)
        progress_dialog.setMinimumDuration(0)
        progress_dialog.setValue(0)
        
        # Match images and annotations
        matched_pairs = []
        unmatched_images = []
        unmatched_annotations = []
        used_annotations = set()  # Keep track of used annotations
        
        # For each image, try to find a matching annotation file
        for image_path in image_files:
            image_name = os.path.splitext(os.path.basename(image_path))[0]
            matching_annotation = None
            
            # Look for annotation file with matching name - FIX: use stricter matching
            for annotation_path in annotation_files:
                if annotation_path in used_annotations:
                    continue  # Skip already used annotations
                
                annotation_name = os.path.splitext(os.path.basename(annotation_path))[0]
                
                # FIX: Use more exact matching - either exact match or specific pattern
                # Either the annotation name contains the image name exactly (not as substring)
                # or it follows a specific pattern like "prefix_imagename_suffix"
                if (annotation_name == image_name or 
                    annotation_name.endswith("_" + image_name) or
                    annotation_name == "Polygon_Annotation_Batch_Exported_by_StomataQuant_" + image_name):
                    matching_annotation = annotation_path
                    used_annotations.add(annotation_path)  # Mark as used
                    break
            
            if matching_annotation:
                matched_pairs.append((image_path, matching_annotation))
            else:
                unmatched_images.append(image_path)
        
        # Find annotations without matching images
        for annotation_path in annotation_files:
            if annotation_path not in used_annotations:
                unmatched_annotations.append(annotation_path)
        
        # Perform import operations
        imported_count = 0
        failed_imports = []
        
        for i, (image_path, annotation_path) in enumerate(matched_pairs):
            # Check for user cancellation
            if progress_dialog.wasCanceled():
                break
                
            # Update progress
            progress_dialog.setValue(i)
            progress_dialog.setLabelText(f"Importing {i+1}/{len(matched_pairs)}: {os.path.basename(image_path)}")
            
            try:
                # Open image
                tab_index = self._open_image(image_path)
                if tab_index >= 0:
                    # Import annotation
                    success = self._import_polygon_annotation(tab_index, annotation_path)
                    if success:
                        imported_count += 1
                    else:
                        failed_imports.append((image_path, annotation_path, "Annotation import failed"))
                else:
                    failed_imports.append((image_path, annotation_path, "Image open failed"))
            except Exception as e:
                failed_imports.append((image_path, annotation_path, f"Error: {str(e)}"))
            
            # Update progress
            progress_dialog.setValue(i + 1)
            QtWidgets.QApplication.processEvents()
        
        # Close progress dialog
        progress_dialog.close()
        
        # Generate report
        report = f"Polygon Annotation Batch Import Results:\n\n"
        report += f"Images found: {len(image_files)}\n"
        report += f"Annotation files found: {len(annotation_files)}\n"
        report += f"Successfully matched pairs: {len(matched_pairs)}\n"
        report += f"Successfully imported: {imported_count}\n\n"
        
        if unmatched_images:
            report += f"Images without matching annotations ({len(unmatched_images)}):\n"
            for path in unmatched_images[:10]:  # Show only first 10 to keep report manageable
                report += f"  - {os.path.basename(path)}\n"
            if len(unmatched_images) > 10:
                report += f"  - ... and {len(unmatched_images) - 10} more files\n"
            report += "\n"
            
        if unmatched_annotations:
            report += f"Annotations without matching images ({len(unmatched_annotations)}):\n"
            for path in unmatched_annotations[:10]:
                report += f"  - {os.path.basename(path)}\n"
            if len(unmatched_annotations) > 10:
                report += f"  - ... and {len(unmatched_annotations) - 10} more files\n"
            report += "\n"
            
        if failed_imports:
            report += f"Failed imports ({len(failed_imports)}):\n"
            for image_path, annotation_path, reason in failed_imports[:10]:
                report += f"  - {os.path.basename(image_path)} - {reason}\n"
            if len(failed_imports) > 10:
                report += f"  - ... and {len(failed_imports) - 10} more file pairs\n"
        
        # Display report
        QtWidgets.QMessageBox.information(
            self.main_window,
            "Batch Import Complete",
            report
        )
    
    def import_rectangles(self):
        """Import rectangle annotations and corresponding images in batch"""
        # Select image directory
        image_dir = QtWidgets.QFileDialog.getExistingDirectory(
            self.main_window, "Select Image Directory", "",
            QtWidgets.QFileDialog.ShowDirsOnly | QtWidgets.QFileDialog.DontResolveSymlinks
        )
        
        if not image_dir:
            return
            
        # Select annotation directory
        annotation_dir = QtWidgets.QFileDialog.getExistingDirectory(
            self.main_window, "Select Rectangle Annotation Directory", "",
            QtWidgets.QFileDialog.ShowDirsOnly | QtWidgets.QFileDialog.DontResolveSymlinks
        )
        
        if not annotation_dir:
            return
            
        # Scan directories for images and annotation files - FIX: avoid duplicates
        image_files = set()  # Use a set to avoid duplicates
        for ext in ['.png', '.jpg', '.jpeg', '.bmp', '.tif']:
            # Find files with both lowercase and uppercase extensions
            found_files = glob.glob(os.path.join(image_dir, f"*{ext}"))
            found_files.extend(glob.glob(os.path.join(image_dir, f"*{ext.upper()}")))
            # Add to set to eliminate duplicates
            image_files.update(found_files)
        
        # Convert back to list
        image_files = list(image_files)
        
        annotation_files = glob.glob(os.path.join(annotation_dir, "*.txt"))
        
        if not image_files:
            QtWidgets.QMessageBox.warning(
                self.main_window,
                "Import Error",
                f"No image files found in the specified directory: {image_dir}"
            )
            return
            
        if not annotation_files:
            QtWidgets.QMessageBox.warning(
                self.main_window,
                "Import Error",
                f"No annotation files found in the specified directory: {annotation_dir}"
            )
            return
        
        # Create progress dialog
        progress_dialog = QtWidgets.QProgressDialog("Importing images and annotations...", "Cancel", 0, len(image_files), self.main_window)
        progress_dialog.setWindowTitle("Batch Import Progress")
        progress_dialog.setWindowModality(QtCore.Qt.WindowModal)
        progress_dialog.setMinimumDuration(0)
        progress_dialog.setValue(0)
        
        # Match images and annotations
        matched_pairs = []
        unmatched_images = []
        unmatched_annotations = []
        used_annotations = set()  # Keep track of used annotations
        
        # For each image, try to find a matching annotation file
        for image_path in image_files:
            image_name = os.path.splitext(os.path.basename(image_path))[0]
            matching_annotation = None
            
            # Look for annotation file with matching name - FIX: use stricter matching
            for annotation_path in annotation_files:
                if annotation_path in used_annotations:
                    continue  # Skip already used annotations
                
                annotation_name = os.path.splitext(os.path.basename(annotation_path))[0]
                
                # FIX: Use more exact matching - either exact match or specific pattern
                # Either the annotation name contains the image name exactly (not as substring)
                # or it follows a specific pattern like "prefix_imagename_suffix"
                if (annotation_name == image_name or 
                    annotation_name.endswith("_" + image_name) or
                    annotation_name == "Rectangle_Annotation_Batch_Exported_by_StomataQuant_" + image_name):
                    matching_annotation = annotation_path
                    used_annotations.add(annotation_path)  # Mark as used
                    break
            
            if matching_annotation:
                matched_pairs.append((image_path, matching_annotation))
            else:
                unmatched_images.append(image_path)
        
        # Find annotations without matching images
        for annotation_path in annotation_files:
            if annotation_path not in used_annotations:
                unmatched_annotations.append(annotation_path)
        
        # Perform import operations
        imported_count = 0
        failed_imports = []
        
        for i, (image_path, annotation_path) in enumerate(matched_pairs):
            # Check for user cancellation
            if progress_dialog.wasCanceled():
                break
                
            # Update progress
            progress_dialog.setValue(i)
            progress_dialog.setLabelText(f"Importing {i+1}/{len(matched_pairs)}: {os.path.basename(image_path)}")
            
            try:
                # Open image
                tab_index = self._open_image(image_path)
                if tab_index >= 0:
                    # Import annotation
                    success = self._import_rectangle_annotation(tab_index, annotation_path)
                    if success:
                        imported_count += 1
                    else:
                        failed_imports.append((image_path, annotation_path, "Annotation import failed"))
                else:
                    failed_imports.append((image_path, annotation_path, "Image open failed"))
            except Exception as e:
                failed_imports.append((image_path, annotation_path, f"Error: {str(e)}"))
            
            # Update progress
            progress_dialog.setValue(i + 1)
            QtWidgets.QApplication.processEvents()
        
        # Close progress dialog
        progress_dialog.close()
        
        # Generate report
        report = f"Rectangle Annotation Batch Import Results:\n\n"
        report += f"Images found: {len(image_files)}\n"
        report += f"Annotation files found: {len(annotation_files)}\n"
        report += f"Successfully matched pairs: {len(matched_pairs)}\n"
        report += f"Successfully imported: {imported_count}\n\n"
        
        if unmatched_images:
            report += f"Images without matching annotations ({len(unmatched_images)}):\n"
            for path in unmatched_images[:10]:
                report += f"  - {os.path.basename(path)}\n"
            if len(unmatched_images) > 10:
                report += f"  - ... and {len(unmatched_images) - 10} more files\n"
            report += "\n"
            
        if unmatched_annotations:
            report += f"Annotations without matching images ({len(unmatched_annotations)}):\n"
            for path in unmatched_annotations[:10]:
                report += f"  - {os.path.basename(path)}\n"
            if len(unmatched_annotations) > 10:
                report += f"  - ... and {len(unmatched_annotations) - 10} more files\n"
            report += "\n"
            
        if failed_imports:
            report += f"Failed imports ({len(failed_imports)}):\n"
            for image_path, annotation_path, reason in failed_imports[:10]:
                report += f"  - {os.path.basename(image_path)} - {reason}\n"
            if len(failed_imports) > 10:
                report += f"  - ... and {len(failed_imports) - 10} more file pairs\n"
        
        # Display report
        QtWidgets.QMessageBox.information(
            self.main_window,
            "Batch Import Complete",
            report
        )
    
    def import_rotated_rectangles(self):
        """Import rotated rectangle annotations and corresponding images in batch"""
        # Select image directory
        image_dir = QtWidgets.QFileDialog.getExistingDirectory(
            self.main_window, "Select Image Directory", "",
            QtWidgets.QFileDialog.ShowDirsOnly | QtWidgets.QFileDialog.DontResolveSymlinks
        )
        
        if not image_dir:
            return
            
        # Select annotation directory
        annotation_dir = QtWidgets.QFileDialog.getExistingDirectory(
            self.main_window, "Select Rotated Rectangle Annotation Directory", "",
            QtWidgets.QFileDialog.ShowDirsOnly | QtWidgets.QFileDialog.DontResolveSymlinks
        )
        
        if not annotation_dir:
            return
            
        # Scan directories for images and annotation files - FIX: avoid duplicates
        image_files = set()  # Use a set to avoid duplicates
        for ext in ['.png', '.jpg', '.jpeg', '.bmp', '.tif']:
            # Find files with both lowercase and uppercase extensions
            found_files = glob.glob(os.path.join(image_dir, f"*{ext}"))
            found_files.extend(glob.glob(os.path.join(image_dir, f"*{ext.upper()}")))
            # Add to set to eliminate duplicates
            image_files.update(found_files)
        
        # Convert back to list
        image_files = list(image_files)
        
        annotation_files = glob.glob(os.path.join(annotation_dir, "*.txt"))
        
        if not image_files:
            QtWidgets.QMessageBox.warning(
                self.main_window,
                "Import Error",
                f"No image files found in the specified directory: {image_dir}"
            )
            return
            
        if not annotation_files:
            QtWidgets.QMessageBox.warning(
                self.main_window,
                "Import Error",
                f"No annotation files found in the specified directory: {annotation_dir}"
            )
            return
        
        # Create progress dialog
        progress_dialog = QtWidgets.QProgressDialog("Importing images and annotations...", "Cancel", 0, len(image_files), self.main_window)
        progress_dialog.setWindowTitle("Batch Import Progress")
        progress_dialog.setWindowModality(QtCore.Qt.WindowModal)
        progress_dialog.setMinimumDuration(0)
        progress_dialog.setValue(0)
        
        # Match images and annotations
        matched_pairs = []
        unmatched_images = []
        unmatched_annotations = []
        used_annotations = set()  # Keep track of used annotations
        
        # For each image, try to find a matching annotation file
        for image_path in image_files:
            image_name = os.path.splitext(os.path.basename(image_path))[0]
            matching_annotation = None
            
            # Look for annotation file with matching name - FIX: use stricter matching
            for annotation_path in annotation_files:
                if annotation_path in used_annotations:
                    continue  # Skip already used annotations
                
                annotation_name = os.path.splitext(os.path.basename(annotation_path))[0]
                
                # FIX: Use more exact matching - either exact match or specific pattern
                # Either the annotation name contains the image name exactly (not as substring)
                # or it follows a specific pattern like "prefix_imagename_suffix"
                if (annotation_name == image_name or 
                    annotation_name.endswith("_" + image_name) or
                    annotation_name == "Rotated_Rectangle_Annotation_Batch_Exported_by_StomataQuant_" + image_name):
                    matching_annotation = annotation_path
                    used_annotations.add(annotation_path)  # Mark as used
                    break
            
            if matching_annotation:
                matched_pairs.append((image_path, matching_annotation))
            else:
                unmatched_images.append(image_path)
        
        # Find annotations without matching images
        for annotation_path in annotation_files:
            if annotation_path not in used_annotations:
                unmatched_annotations.append(annotation_path)
        
        # Perform import operations
        imported_count = 0
        failed_imports = []
        
        for i, (image_path, annotation_path) in enumerate(matched_pairs):
            # Check for user cancellation
            if progress_dialog.wasCanceled():
                break
                
            # Update progress
            progress_dialog.setValue(i)
            progress_dialog.setLabelText(f"Importing {i+1}/{len(matched_pairs)}: {os.path.basename(image_path)}")
            
            try:
                # Open image
                tab_index = self._open_image(image_path)
                if tab_index >= 0:
                    # Import annotation
                    success = self._import_rotated_rectangle_annotation(tab_index, annotation_path)
                    if success:
                        imported_count += 1
                    else:
                        failed_imports.append((image_path, annotation_path, "Annotation import failed"))
                else:
                    failed_imports.append((image_path, annotation_path, "Image open failed"))
            except Exception as e:
                failed_imports.append((image_path, annotation_path, f"Error: {str(e)}"))
            
            # Update progress
            progress_dialog.setValue(i + 1)
            QtWidgets.QApplication.processEvents()
        
        # Close progress dialog
        progress_dialog.close()
        
        # Generate report
        report = f"Rotated Rectangle Annotation Batch Import Results:\n\n"
        report += f"Images found: {len(image_files)}\n"
        report += f"Annotation files found: {len(annotation_files)}\n"
        report += f"Successfully matched pairs: {len(matched_pairs)}\n"
        report += f"Successfully imported: {imported_count}\n\n"
        
        if unmatched_images:
            report += f"Images without matching annotations ({len(unmatched_images)}):\n"
            for path in unmatched_images[:10]:
                report += f"  - {os.path.basename(path)}\n"
            if len(unmatched_images) > 10:
                report += f"  - ... and {len(unmatched_images) - 10} more files\n"
            report += "\n"
            
        if unmatched_annotations:
            report += f"Annotations without matching images ({len(unmatched_annotations)}):\n"
            for path in unmatched_annotations[:10]:
                report += f"  - {os.path.basename(path)}\n"
            if len(unmatched_annotations) > 10:
                report += f"  - ... and {len(unmatched_annotations) - 10} more files\n"
            report += "\n"
            
        if failed_imports:
            report += f"Failed imports ({len(failed_imports)}):\n"
            for image_path, annotation_path, reason in failed_imports[:10]:
                report += f"  - {os.path.basename(image_path)} - {reason}\n"
            if len(failed_imports) > 10:
                report += f"  - ... and {len(failed_imports) - 10} more file pairs\n"
        
        # Display report
        QtWidgets.QMessageBox.information(
            self.main_window,
            "Batch Import Complete",
            report
        )
    
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
                if tab.property("file_path") == file_path:
                    # Already open, return the index
                    return i
            
            # Read the image
            reader = QImageReader(file_path)
            if reader.canRead():
                image = reader.read()
                pixmap = QPixmap.fromImage(image)
                if pixmap.isNull():
                    print(f"Cannot load image: {file_path}")
                    return -1
            else:
                print(f"Cannot read image: {file_path}")
                return -1

            # Create new tab
            tab = QWidget()
            tab.setProperty("file_path", file_path)
            
            # Create ImageGraphicsView
            graphics_view = ImageGraphicsView(tab)
            graphics_view.load_image(file_path)
            
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
            self.main_window.tabWidget.setCurrentIndex(tab_index)

                        # 添加以下代码修复缩放问题
            # ------ 新增代码开始 ------
            # 调用fit_to_view来适应视图大小
            graphics_view.fit_to_view_custom()
            
            # 更新缩放信息显示
            self.main_window.update_zoom_on_tab_change(tab_index)
            # ------ 新增代码结束 ------
            QtWidgets.QApplication.processEvents()  # Ensure UI updates
            
            return tab_index
        except Exception as e:
            print(f"Error opening image: {e}")
            return -1
    
    def _import_polygon_annotation(self, tab_index, annotation_path):
        """
        Import polygon annotations to the specified tab
        
        Args:
            tab_index: Tab index where the annotation should be imported
            annotation_path: Path to the annotation file
            
        Returns:
            bool: True if import was successful, False otherwise
        """
        try:
            # Get tab and canvas
            tab = self.main_window.tabWidget.widget(tab_index)
            if not tab:
                return False
                
            graphics_view = tab.property("graphics_view")
            if not graphics_view or not graphics_view.canvas:
                return False
                
            canvas = graphics_view.canvas
            
            # Get image dimensions for normalization
            image_width = canvas.image_size.width()
            image_height = canvas.image_size.height()
            
            # Read the annotation file
            with open(annotation_path, 'r') as f:
                lines = f.readlines()
            
            # Parse and add shapes
            shapes_added = 0
            
            for line in lines:
                line = line.strip()
                if not line:
                    continue
                
                try:
                    # Try to parse as YOLO polygon format: <class> <x1> <y1> <x2> <y2> ... <xn> <yn>
                    parts = line.split()
                    if len(parts) < 5:  # Need at least a class and 2 points (4 coords)
                        continue
                        
                    # Extract class number
                    classnum = int(parts[0])
                    
                    # Parse coordinates
                    points = []
                    for i in range(1, len(parts), 2):
                        try:
                            # Denormalize coordinates from YOLO format
                            x = float(parts[i]) * image_width
                            y = float(parts[i+1]) * image_height
                            points.append(QPointF(x, y))
                        except (ValueError, IndexError):
                            continue
                    
                    if len(points) < 3:  # Polygons need at least 3 points
                        continue
                    
                    # Get label based on class number
                    label = f"class_{classnum}"
                    
                    # Assign group_id
                    # Find the maximum group_id for shapes with the same classnum
                    same_class_shapes = [s for s in canvas.shapes if s.classnum == classnum]
                    group_id = 0
                    if same_class_shapes:
                        group_id = max(s.group_id for s in same_class_shapes) + 1
                    
                    # Create shape
                    shape = Shape(
                        label=label,
                        classnum=classnum,
                        pointslist=points,
                        shape_type='polygon',
                        group_id=group_id,
                        scale_factor=canvas.scale_factor
                    )
                    
                    # Add to canvas
                    canvas.shapes.append(shape)
                    shapes_added += 1
                    
                except Exception as e:
                    print(f"Error parsing annotation line: {e}")
                    continue
            
            # Update UI if shapes were added
            if shapes_added > 0:
                # Update canvas
                canvas.update()
                canvas.shapesChanged.emit()
                
                # Update UI elements
                try:
                    self.main_window.update_shapes_and_label_list()
                except Exception as e:
                    print(f"Error updating UI after import: {e}")
                
                return True
                
            return False
            
        except Exception as e:
            print(f"Error importing polygon annotation: {e}")
            return False
    
    def _import_rectangle_annotation(self, tab_index, annotation_path):
        """
        Import rectangle annotations to the specified tab
        
        Args:
            tab_index: Tab index where the annotation should be imported
            annotation_path: Path to the annotation file
            
        Returns:
            bool: True if import was successful, False otherwise
        """
        try:
            # Get tab and canvas
            tab = self.main_window.tabWidget.widget(tab_index)
            if not tab:
                return False
                
            graphics_view = tab.property("graphics_view")
            if not graphics_view or not graphics_view.canvas:
                return False
                
            canvas = graphics_view.canvas
            
            # Get image dimensions for normalization
            image_width = canvas.image_size.width()
            image_height = canvas.image_size.height()
            
            # Read the annotation file
            with open(annotation_path, 'r') as f:
                lines = f.readlines()
            
            # Parse and add shapes
            shapes_added = 0
            
            for line in lines:
                line = line.strip()
                if not line:
                    continue
                
                try:
                    # Try to parse as YOLO box format: <class> <center_x> <center_y> <width> <height>
                    parts = line.split()
                    if len(parts) != 5:
                        continue
                        
                    # Extract class number
                    classnum = int(parts[0])
                    
                    # Parse rectangle coordinates
                    center_x = float(parts[1]) * image_width
                    center_y = float(parts[2]) * image_height
                    width = float(parts[3]) * image_width
                    height = float(parts[4]) * image_height
                    
                    # Calculate top-left and bottom-right points
                    x1 = center_x - width / 2
                    y1 = center_y - height / 2
                    x2 = center_x + width / 2
                    y2 = center_y + height / 2
                    
                    # Create points for rectangle
                    points = [QPointF(x1, y1), QPointF(x2, y2)]
                    
                    # Get label based on class number
                    label = f"class_{classnum}"
                    
                    # Assign group_id
                    # Find the maximum group_id for shapes with the same classnum
                    same_class_shapes = [s for s in canvas.shapes if s.classnum == classnum]
                    group_id = 0
                    if same_class_shapes:
                        group_id = max(s.group_id for s in same_class_shapes) + 1
                    
                    # Create shape
                    shape = Shape(
                        label=label,
                        classnum=classnum,
                        pointslist=points,
                        shape_type='rectangle',
                        group_id=group_id,
                        scale_factor=canvas.scale_factor
                    )
                    
                    # Add to canvas
                    canvas.shapes.append(shape)
                    shapes_added += 1
                    
                except Exception as e:
                    print(f"Error parsing rectangle annotation line: {e}")
                    continue
            
            # Update UI if shapes were added
            if shapes_added > 0:
                # Update canvas
                canvas.update()
                canvas.shapesChanged.emit()
                
                # Update UI elements
                try:
                    self.main_window.update_shapes_and_label_list()
                except Exception as e:
                    print(f"Error updating UI after import: {e}")
                
                return True
                
            return False
            
        except Exception as e:
            print(f"Error importing rectangle annotation: {e}")
            return False
    
    def _import_rotated_rectangle_annotation(self, tab_index, annotation_path):
        """
        Import rotated rectangle annotations to the specified tab
        
        Args:
            tab_index: Tab index where the annotation should be imported
            annotation_path: Path to the annotation file
            
        Returns:
            bool: True if import was successful, False otherwise
        """
        try:
            # Get tab and canvas
            tab = self.main_window.tabWidget.widget(tab_index)
            if not tab:
                return False
                
            graphics_view = tab.property("graphics_view")
            if not graphics_view or not graphics_view.canvas:
                return False
                
            canvas = graphics_view.canvas
            
            # Get image dimensions for normalization
            image_width = canvas.image_size.width()
            image_height = canvas.image_size.height()
            
            # Read the annotation file
            with open(annotation_path, 'r') as f:
                lines = f.readlines()
            
            # Parse and add shapes
            shapes_added = 0
            
            for line in lines:
                line = line.strip()
                if not line:
                    continue
                
                try:
                    # Try to parse as YOLO OBB format: <class> <x1> <y1> <x2> <y2> <x3> <y3> <x4> <y4>
                    parts = line.split()
                    if len(parts) != 9:  # Class + 4 points (8 coords)
                        continue
                        
                    # Extract class number
                    classnum = int(parts[0])
                    
                    # Parse coordinates for the 4 points of rotated rectangle
                    points = []
                    for i in range(1, 9, 2):
                        # Denormalize coordinates from YOLO format
                        x = float(parts[i]) * image_width
                        y = float(parts[i+1]) * image_height
                        points.append(QPointF(x, y))
                    
                    if len(points) != 4:  # Rotated rectangles need exactly 4 points
                        continue
                    
                    # Get label based on class number
                    label = f"class_{classnum}"
                    
                    # Assign group_id
                    # Find the maximum group_id for shapes with the same classnum
                    same_class_shapes = [s for s in canvas.shapes if s.classnum == classnum]
                    group_id = 0
                    if same_class_shapes:
                        group_id = max(s.group_id for s in same_class_shapes) + 1
                    
                    # Create shape
                    shape = Shape(
                        label=label,
                        classnum=classnum,
                        pointslist=points,
                        shape_type='rotated_rectangle',
                        group_id=group_id,
                        scale_factor=canvas.scale_factor
                    )
                    
                    # Add to canvas
                    canvas.shapes.append(shape)
                    shapes_added += 1
                    
                except Exception as e:
                    print(f"Error parsing rotated rectangle annotation line: {e}")
                    continue
            
            # Update UI if shapes were added
            if shapes_added > 0:
                # Update canvas
                canvas.update()
                canvas.shapesChanged.emit()
                
                # Update UI elements
                try:
                    self.main_window.update_shapes_and_label_list()
                except Exception as e:
                    print(f"Error updating UI after import: {e}")
                
                return True
                
            return False
            
        except Exception as e:
            print(f"Error importing rotated rectangle annotation: {e}")
            return False