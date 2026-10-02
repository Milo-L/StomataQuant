import sys
from macos_paths import macos_output_dir, macos_resource_path

if sys.platform == 'darwin' and __name__ == '__main__' and getattr(sys, 'frozen', False):
    # In a frozen .app, sys.executable is the app launcher rather than Python.
    import multiprocessing
    multiprocessing.freeze_support()
    if len(sys.argv) > 1 and sys.argv[1] == '--stomataquant-worker':
        from inference_worker import batch_main, main as inference_main
        if len(sys.argv) == 4 and sys.argv[2] == '--batch':
            batch_main(sys.argv[3])
        elif len(sys.argv) == 4:
            inference_main(sys.argv[2], sys.argv[3])
        else:
            raise ValueError('Invalid inference worker arguments.')
        raise SystemExit(0)

from annotation_io import (validate_polygon_export,
                           validate_rectangle_export, parse_annotation_line, parse_rectangle_table_line,
                           rectangle_table_header_index, import_warning,
                           require_annotation_text)
from annotation_session import snapshot as annotation_snapshot, save as save_annotation_session, load as load_annotation_session, session_path
# -*- coding: utf-8 -*-
import sys
import os
import io
import math
import ctypes
import importlib.util  # 引入底层模块查找工具
from pathlib import Path

# 找到当前脚本所在目录 (也就是 app/src 目录)
SRC_DIR = os.path.dirname(os.path.abspath(__file__))
# 找到 app 根目录 (向上一级)
APP_ROOT = os.path.dirname(SRC_DIR)
# 封装的 Python 根目录
PYTHON_ROOT = os.path.join(APP_ROOT, "python")
# 封装的 site-packages 路径
LOCAL_SP = os.path.join(PYTHON_ROOT, "Lib", "site-packages")

# ================= 环境嗅探：判断是打包环境还是开发环境 =================
is_packaged_env = (sys.platform == 'win32' and sys.executable.startswith(PYTHON_ROOT)
                   and os.path.exists(PYTHON_ROOT))

if is_packaged_env:
    print("----------------------------------------------------------------")
    print("✨ [StomataQuant] 欢迎使用！祝您实验顺利，科研成果喜提顶刊！")
    print("✨ Welcome to StomataQuant! Wishing you smooth experiments and high-impact publications!")
    print(f"📧 合作与建议 (Collab/Ideas): milo.liu@stu.pku.edu.cn | GitHub: https://github.com/Milo-L/StomataQuant")
    print("----------------------------------------------------------------")
    os.environ["PYTHONHOME"] = PYTHON_ROOT

    clean_sys_path = [SRC_DIR]
    LIB_DIR = os.path.join(PYTHON_ROOT, "Lib")
    clean_sys_path.append(LIB_DIR) 

    for p in sys.path:
        if p.lower().startswith(PYTHON_ROOT.lower()) or p.endswith('.zip'):
            if p not in clean_sys_path:  
                clean_sys_path.append(p)

    sys.path = clean_sys_path

    if LOCAL_SP not in sys.path:
        sys.path.insert(1, LOCAL_SP) 

    LOCAL_SCRIPTS = os.path.join(PYTHON_ROOT, "Scripts")
    os.environ["PATH"] = f"{PYTHON_ROOT}{os.pathsep}{LOCAL_SCRIPTS}{os.pathsep}{LOCAL_SP}{os.pathsep}" + os.environ.get("PATH", "")
else:
    print("🛠️ [StomataQuant] 检测到开发环境：欢迎大佬改造，愿 Bug 随风去，灵感永不断！")
    print("🛠️ Dev Mode: Welcome to modify! May your code be bug-free and inspiration never-ending.")
    print(f"🤝 合作与建议 (Collab/Ideas): milo.liu@stu.pku.edu.cn | https://github.com/Milo-L/StomataQuant")
    print(f"🚀 Running on: {sys.executable}")
    print("----------------------------------------------------------------")
    if SRC_DIR not in sys.path:
        sys.path.insert(0, SRC_DIR)

if sys.platform == 'win32':
    # ================= PyQt5 插件及底层依赖配置 (终极自适应版) =================
    def get_safe_windows_path(path):
        if not sys.platform.startswith("win"):
            return path
        try:
            buf_size = ctypes.windll.kernel32.GetShortPathNameW(path, None, 0)
            if buf_size > 0:
                buf = ctypes.create_unicode_buffer(buf_size)
                ctypes.windll.kernel32.GetShortPathNameW(path, buf, buf_size)
                return buf.value
        except Exception as e:
            print(f"短路径转换失败，回退原路径: {e}")
        return path

    # 清理旧环境变量
    if 'QT_PLUGIN_PATH' in os.environ:
        del os.environ['QT_PLUGIN_PATH']
    if 'QT_QPA_PLATFORM_PLUGIN_PATH' in os.environ:
        del os.environ['QT_QPA_PLATFORM_PLUGIN_PATH']

    # 【核心修复】：智能探测是 Qt5 还是 Qt 文件夹！

    pyqt5_spec = importlib.util.find_spec('PyQt5')
    raw_plugin_path = ""

    if pyqt5_spec and pyqt5_spec.submodule_search_locations:
        pyqt5_dir = pyqt5_spec.submodule_search_locations[0]
    
        # 路径 A: 标准 Pip 安装路径 (新版)
        p_pip_new = os.path.join(pyqt5_dir, 'Qt5', 'plugins')
        # 路径 B: 标准 Pip 安装路径 (旧版)
        p_pip_old = os.path.join(pyqt5_dir, 'Qt', 'plugins')
        # 路径 C: 你现在的 Anaconda 环境路径 (关键！)
        # 它在 site-packages 的上两级目录下的 Library/plugins
        p_conda = os.path.abspath(os.path.join(pyqt5_dir, "..", "..", "..", "Library", "plugins"))

        if os.path.exists(p_pip_new):
            raw_plugin_path = p_pip_new
        elif os.path.exists(p_pip_old):
            raw_plugin_path = p_pip_old
        elif os.path.exists(p_conda):
            raw_plugin_path = p_conda

    # 如果上面都没搜到（比如打包环境），再使用兜底路径
    if not raw_plugin_path:
        raw_plugin_path = os.path.join(LOCAL_SP, "PyQt5", "Qt5", "plugins")


    # 获取短路径别名
    safe_plugin_path = get_safe_windows_path(raw_plugin_path)
    safe_platforms_path = os.path.join(safe_plugin_path, 'platforms')

    # 关键防错拦截：确保探测到的路径确实存在，再交给环境变量
    if os.path.exists(safe_plugin_path):
        os.environ['QT_PLUGIN_PATH'] = safe_plugin_path
        os.environ["QT_QPA_PLATFORM_PLUGIN_PATH"] = safe_platforms_path
        print(f"============================== 成功挂载 QT_PLUGIN_PATH: {os.environ['QT_PLUGIN_PATH']}")
    else:
        print(f"【严重警告】：插件路径不存在！{safe_plugin_path}")

elif sys.platform == 'darwin':
    # PyQt5 or the .app packager discovers the Cocoa plugin.
    pass

# ================= 现在才可以安全导入 PyQt5 =================
from PyQt5.QtCore import Qt, QTimer, QEventLoop, QPluginLoader, QCoreApplication, QtMsgType, qInstallMessageHandler
from PyQt5.QtGui import QImageReader
import PyQt5

# 强行将正确的安全路径写入 PyQt5 核心
if sys.platform == 'win32' and os.path.exists(safe_plugin_path):
    QCoreApplication.addLibraryPath(safe_plugin_path)

print("The loaded library path：", QCoreApplication.libraryPaths())

# 检查支持的图像格式
formats = QImageReader.supportedImageFormats()
print("Supported Formats:", formats)
# ===============================================================================

# 导入核心包 Import core packages
import gc
import tempfile
import json
import time
from collections import defaultdict
from PyQt5 import QtCore, QtGui, QtWidgets, sip
from PyQt5.QtCore import QPointF, QRect, QRectF, Qt, pyqtSignal, QThread,QFile, QIODevice
from PyQt5.QtGui import (QFont, QImage, QKeySequence, QPixmap, QTransform)
from PyQt5.QtWidgets import (QApplication, QDialog, QFileDialog, QLabel, QLineEdit, QMessageBox,
                             QProgressBar, QShortcut, QSplashScreen, QVBoxLayout, QWidget,QProgressDialog)


# 导入自定义模块 Import custom modules
from StomataQuant_GUI import MainWindow
from toolbar_ui import style_button
from ultralytics import YOLO
from AllDialogs import InferenceSettingsDialog,SetMeasuringScaleDialog,LabelInputDialog,ProgressDialog,DisplaySettingsDialog,HeatMapDialog,BatchProcessingDialog,BatchProgressDialog
from ImageGraphicsView import ImageGraphicsView
from shape import *
from measurements import resolve_scale, ensure_features, refresh_shapes, apply_scale, positive_number
from measurement_controller import MeasurementController
from canvas import Canvas, USE_NUMBA, check_numba,process_polygon_data
from dock_widgets import ShapeListDock, LabelListDock,MeasuredResultsDock,ImageResultsSummaryDock
from InferenceThread import YOLOSegInferenceThread,PolygonProcessThread,ABorADInferenceThread, HeatMapGenerationThread
from BatchProcessor import BatchProcessor, BatchExporter, BatchImporter, BatchFeatureExporter
import display_settings as display
from point_annotations import (write_points, import_points,
                               require_target, refresh_point_import, import_checkpoint)
from task_support import task_manager, OperationCancelled
from inference_support import decode_predictions, shapes_from_predictions, save_polygon_audit
from safe_io import write_text_atomic, source_suffix
from geometry import minimum_rectangle_size
import resources_rc
#############################################################################################################
# UIMainWindow
# 主窗口类，继承自MainWindow
#############################################################################################################

class UIMainWindow(MainWindow):
    metadataCommit = QtCore.pyqtSignal(object, str, str)
    def __init__(self):
        super().__init__()
        if not check_numba():
            import canvas as canvas_module
            canvas_module.USE_NUMBA = False
            print("Numba is unavailable and acceleration has been disabled.")
        self.setupUi(self)
        self._discard_unsaved_for_session = False
        self._open_dropped_images_for_session = False
        self._drop_annotation_mode_for_session = None
        self.setAcceptDrops(True)
        self.tabWidget.setAcceptDrops(True)
        self.tabWidget.installEventFilter(self)
        self.tabWidget.tabBar().setAcceptDrops(True)
        self.tabWidget.tabBar().installEventFilter(self)
        self.load_color_settings()
        display.set_current(display.load(QtCore.QSettings("StomaQuant", "GUI")))
        self._noShapeListSelectionSlot = False
        self._noCanvasSelectionSlot = False
        # 添加全局状态变量控制 group_id 是否显示
        self._global_show_group_id = False

        # 初始化 MeasuredResultsDock

        self.image_results_summary_dock = ImageResultsSummaryDock(self)
        self.addDockWidget(Qt.RightDockWidgetArea, self.image_results_summary_dock)
        self.measured_results_dock = MeasuredResultsDock(self)
        self.measurement_controller = MeasurementController(self)
        self.measured_results_dock.shapeSelectionChanged.connect(self.on_shape_selected_in_dock)
        self.addDockWidget(Qt.RightDockWidgetArea, self.measured_results_dock)
        # 初始化 ShapeListDock
        self.shapedockinstance = ShapeListDock(self)
        self.addDockWidget(Qt.RightDockWidgetArea, self.shapedockinstance)
        # 初始化 LabelListDock
        self.labeldockinstance = LabelListDock(self)
        self.addDockWidget(Qt.RightDockWidgetArea, self.labeldockinstance)

        self.actionHeatMap.triggered.connect(self.show_heatmap)
        # 菜单栏按钮
        # 链接Open 按钮到open_file
        self.actionDisplaySettings.triggered.connect(self.show_display_settings)
        self.actionOpen.triggered.connect(self.open_file)
        self.actionOpenFolder.triggered.connect(self.open_folder)
        self.opened_files = []  # 以跟踪打开的文件，防止重复添加文件
        ## 链接到保存按钮
        self.actionSavePolygonAnnotataion.triggered.connect(self.save_polygon_annotation)
        self.actionImportPolygonAnnotataion.triggered.connect(self.import_polygon)
        self.actionSaveRectangleAnnotataion.triggered.connect(self.save_rectangle_annotation)
        self.actionImportRectangleAnnotataion.triggered.connect(self.import_rectangle)
        self.actionSaveRotatedRectangleAnnotataion.triggered.connect(self.save_rotated_rectangle_annotation)
        self.actionImportRotatedRectangleAnnotataion.triggered.connect(self.import_rotated_rectangle)
        self.actionSavePointAnnotataion.triggered.connect(self.save_point_annotation)
        self.actionImportPointAnnotataion.triggered.connect(self.import_point)
        self.actionShowPoint.triggered.connect(self.show_points)
        self.actionShowID.triggered.connect(self.draw_group_id)

        # 链接到模型选择
        self.actionModelSetting.triggered.connect(self.load_model)  
        self.model = None  # Initialize the model attribute
        self.update_model_status()
        # 链接到推理设置
        self.actionInferenceSetting.triggered.connect(self.show_inference_settings)  # Connect to show inference settings
        self.inference_settings = {}  # Initialize inference settings attribute
        # 链接到模型推理
        self.actionAI.triggered.connect(self.run_YOLO_seg_inference)
        
        # 工具栏按钮
        # 连接滑动条的值变化信号到 zoom_slider_changed
        self.zoomSlider.valueChanged.connect(self.zoom_slider_changed)
        # 连接 QLineEdit 的编辑完成信号到 update_zoom_slider
        self.zoomLineEdit.editingFinished.connect(self.update_zoom_slider)
        # 链接Original Size 按钮
        self.actionResetZoom.triggered.connect(self.reset_zoom)
        # 链接Fit to View 按钮
        self.actionZoom.triggered.connect(self.fit_to_view)  

        # 切换标签或者关闭标签
        # 切换标签链接到 on_tab_changed_and_update_zoom_and_list
        self.tabWidget.currentChanged.connect(self.on_tab_changed_and_update_zoom_and_list)
        self.tabWidget.currentChanged.connect(self.update_image_status)
        self.tabWidget.tabCloseRequested.connect(self.close_tab)

        # # 链接shapedockinstance中选中某个列信号到on_shape_selected_in_dock
        self.shapedockinstance.selectionClickedinShapeList.connect(self.on_shape_selected_in_dock)
        
        # 链接shapedockinstance中可视性更改信号到update_canvas
        self.shapedockinstance.visibilityChanged.connect(self.update_canvas)
        self.shapedockinstance.pointClassChanged.connect(self.change_point_class)
        self.shapedockinstance.metadataEdited.connect(self._queue_metadata_edit)
        self.labeldockinstance.metadataEdited.connect(self._queue_metadata_edit)
        self.metadataCommit.connect(self._apply_metadata_edit, Qt.QueuedConnection)
        # 链接labeldockinstance中可视性更改信号到on_label_visibility_changed
        self.labeldockinstance.visibilityChanged.connect(self.on_label_visibility_changed)
        # 连接动作
        self.actionGetMER.triggered.connect(self.Get_MER_on_Canvas)
        self.actionDuplicate.triggered.connect(self.duplicate_shape)

        self.actionUndo.setShortcut(QKeySequence('Ctrl+Z'))
        self.actionUndo.setToolTip('Undo (Ctrl+Z)')
        self.actionUndo.setIcon(self._history_icon(False))
        self.actionRedo = QtWidgets.QAction('Redo', self)
        self.actionRedo.setShortcut(QKeySequence('Ctrl+Y'))
        self.actionRedo.setToolTip('Redo (Ctrl+Y)')
        self.actionRedo.setIcon(self._history_icon(True))
        self.actionRedo.setEnabled(False)
        self.toolBar.insertAction(self.historySeparator, self.actionRedo)
        style_button(self.toolBar.widgetForAction(self.actionRedo), icon_only=True)
        self.actionRedo.triggered.connect(self.redo)
        self.actionEditShapes.setToolTip('Edit Shapes (Alt+click cycles overlapping shapes)')

        self.actionDelete.triggered.connect(self.delete_selected_shape)
        self.actionDeleteAllShapes.triggered.connect(self.delete_all_shapes)
        self.actionUndo.triggered.connect(self.undo)

        # 连接创建形状的动作
        self.actionCreatePolygon.triggered.connect(self.create_polygon)
        self.actionCreateRotatedRectangle.triggered.connect(self.create_rotated_rectangle)
        self.actionCreateRectangle.triggered.connect(self.create_rectangle)
        self.actionCreateLine.triggered.connect(self.create_line)
        self.actionCreatePoint.triggered.connect(self.create_point)


        
        self.actionABorAD.triggered.connect(self.inference_ABorAD)  
        self.actionSetMeasuringScale.triggered.connect(self.set_measuring_scale)

        self.actionFilterAllEdges.triggered.connect(self.shape_AllEdges_filter)
        self.actionFilterTopLeft.triggered.connect(self.shape_TopLeft_filter)
        self.actionFilterRightBottom.triggered.connect(self.shape_RightBottom_filter)
        self.actionEditShapes.triggered.connect(self.edit_shapes)
        self.actionClose.triggered.connect(self.close_application)

        self.actionBatchProcessing.triggered.connect(self.batch_processing)

        self.actionBatchExportPolygon.triggered.connect(self.batch_export_polygon)
        self.actionBatchExportRectangle.triggered.connect(self.batch_export_rectangle)
        self.actionBatchExportRotatedRectangle.triggered.connect(self.batch_export_rotated_rectangle)
        self.actionBatchImportPolygon.triggered.connect(self.batch_import_polygon)
        self.actionBatchImportRectangle.triggered.connect(self.batch_import_rectangle)
        self.actionBatchImportRotatedRectangle.triggered.connect(self.batch_import_rotated_rectangle)
        self.actionBatchExportPoint.triggered.connect(self.batch_export_point)
        self.actionBatchImportPoint.triggered.connect(self.batch_import_point)
        
        self.actionExportPolygonFeature.triggered.connect(lambda: self.batch_export_features('polygon'))
        self.actionExportRotatedRectangleFeature.triggered.connect(lambda: self.batch_export_features('rotated_rectangle'))
        self.actionExportRectangleFeature.triggered.connect(lambda: self.batch_export_features('rectangle'))
        self.actionExportPointFeature.triggered.connect(lambda: self.batch_export_features('point'))

                # 在__init__方法的末尾添加
        self.actionShortcutHelp.triggered.connect(self.show_shortcut_help)
        self.actionSeeHelp.triggered.connect(self.show_help)
        from keyboard_shortcuts import ShortcutController
        self._shortcut_controller = ShortcutController(self)
    
    def batch_export_features(self, shape_type):
        """
        批量导出指定形状类型的特征
        Args:
            shape_type: 'polygon', 'rotated_rectangle', 'rectangle', 'point'
        """
        exporter = BatchFeatureExporter(self)
        exporter.export_features(shape_type)

    def show_help(self):
        """使用系统默认浏览器打开 StomataQuant 的 GitHub 页面"""
        import webbrowser
        
        # 打开 StomataQuant 的 GitHub 页面
        github_url = "https://github.com/Milo-L/StomataQuant"
        
        try:
            webbrowser.open(github_url)
        except Exception as e:
            from PyQt5.QtWidgets import QMessageBox
            QMessageBox.warning(self, "Failed to open browser", f"Cannot open the default browser: {str(e)}, please visit {github_url} manually.")
    
    def show_shortcut_help(self):
        from keyboard_shortcuts import ShortcutHelpDialog
        if hasattr(self, 'shortcut_dialog') and self.shortcut_dialog.isVisible():
            self.shortcut_dialog.raise_()
            self.shortcut_dialog.activateWindow()
            return
        self.shortcut_dialog = ShortcutHelpDialog(self, self._shortcut_controller.rows())
        self.shortcut_dialog.show()

    def batch_import_point(self):
        try:
            return BatchImporter(self).import_points()
        except Exception as error:
            QMessageBox.critical(self, 'Batch import error', f'Failed to import Point annotations: {error}')

    def batch_export_point(self):
        try:
            return BatchExporter(self).export_points()
        except Exception as error:
            QMessageBox.critical(self, 'Export error', f'Failed to export Point annotations: {error}')

    def batch_import_polygon(self):
        """批量导入多边形标注和对应图像"""
        try:
            batch_importer = BatchImporter(self)
            batch_importer.import_polygons()
        except Exception as e:
            QMessageBox.critical(
                self,
                "Batch import error",
                f"An error occurred during batch import of polygon annotations: {str(e)}"
            )

    def batch_import_rectangle(self):
        """批量导入矩形标注和对应图像"""
        try:
            batch_importer = BatchImporter(self)
            batch_importer.import_rectangles()
        except Exception as e:
            QMessageBox.critical(
                self,
                "Batch import error",
                f"An error occurred during batch import of rectangle annotations: {str(e)}"
            )

    def batch_import_rotated_rectangle(self):
        """批量导入旋转矩形标注和对应图像"""
        try:
            batch_importer = BatchImporter(self)
            batch_importer.import_rotated_rectangles()
        except Exception as e:
            QMessageBox.critical(
                self,
                "Batch import error",
                f"An error occurred during batch import of rotated rectangle annotations: {str(e)}"
            )
    
    # 修改批量导出方法如下:
    def batch_export_polygon(self):
        """批量导出所有标签页中的多边形标注"""
        try:
            # 创建批量导出器实例
            batch_exporter = BatchExporter(self)
            batch_exporter.export_polygons()
        except Exception as e:
            QMessageBox.critical(self, "Export error", f"An error occurred while batch-exporting polygons: {str(e)}")

    def batch_export_rectangle(self):
        """批量导出所有标签页中的矩形标注"""
        try:
            # 创建批量导出器实例
            batch_exporter = BatchExporter(self)
            batch_exporter.export_rectangles()
        except Exception as e:
            QMessageBox.critical(self, "Export error", f"An error occurred while batch-exporting rectangles: {str(e)}")

    def batch_export_rotated_rectangle(self):
        """批量导出所有标签页中的旋转矩形标注"""
        try:
            # 创建批量导出器实例
            batch_exporter = BatchExporter(self)
            batch_exporter.export_rotated_rectangles()
        except Exception as e:
            QMessageBox.critical(self, "Export error", f"An error occurred while batch-exporting the rotated rectangles: {str(e)}")
    
    def batch_processing(self):
        """调用批处理器处理所有打开的标签页"""
        if self.tabWidget.count() < 2:
            QMessageBox.warning(self, 'Batch Processing',
                                'Batch Processing requires at least two open images/tabs.')
            return
        try:
            BatchProcessor(self).process()
        except Exception as error:
            QMessageBox.warning(self, 'Error', f'Error during batch processing: {error}')

    ### 功能实现，关闭程序 terminate the program
    def close_application(self):
        reply = QMessageBox.question(
            self,
            "Confirm Exit",
            "Are you sure you want to exit?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            self.close()

    ### 启动Edit模式，控制其他按钮开启还是关闭
    ### Start the Edit mode and control whether other buttons are enabled or disabled.
    def edit_shapes(self):
        try:
            currentshapes = self.get_current_shapes()
            has_shapes = bool(self.get_current_shapes())
            self.actionDeleteAllShapes.setEnabled(has_shapes)
            has_polygons = any([s.shape_type == "polygon" for s in self.get_current_shapes()])
            self.actionGetMER.setEnabled(has_polygons)

            if not currentshapes:
                QMessageBox.warning(self, "Notice", "Currently, there are no editable shapes. Please create a shape first.")
                self.actionEditShapes.setChecked(False)
                self.actionFilterAllEdges.setEnabled(False)
                self.actionFilterTopLeft.setEnabled(False)
                self.actionFilterRightBottom.setEnabled(False)
            else:
                self.actionEditShapes.setChecked(True)
                self.actionFilterAllEdges.setEnabled(True)
                self.actionFilterTopLeft.setEnabled(True)
                self.actionFilterRightBottom.setEnabled(True)
                self.get_current_graphics_view().canvas.set_mode('edit')
        except Exception as e:
            QMessageBox.warning(self, "Error", "Currently no image is open, please open an image first.")
            self.actionEditShapes.setChecked(False)
            return

    ### 比例尺设置按键 关于比例尺的设置
    ### Regarding the Setting of Scale
    def set_measuring_scale(self):
        SetMeasuringScaleDialog(self).exec_()

    ###“Feature Extraction”按键所连接的功能： 关于各种形状的特征提取，主要依赖于shape中定义的方法
    ### The function connected by the "Feature Extraction" button:
    # Regarding the feature extraction of various shapes, it mainly relies on the methods defined in the "shape" section.
    def refresh_measurements(self, force=False):
        if getattr(self, '_defer_batch_refresh', False):
            return
        view = self.get_current_graphics_view()
        canvas = view.canvas if view else None
        self.measurement_controller.bind(canvas)
        if canvas is None:
            return
        if getattr(canvas, '_edit_before', None) is not None:
            self.schedule_measurement_refresh()
            return
        if hasattr(self, '_measurement_timer'):
            self._measurement_timer.stop()
        if (getattr(self, '_drop_batch_background', False)
                or canvas in self.measurement_controller.batch_managed):
            self.measurement_controller.enqueue_batch_tab(self.tabWidget.currentWidget())
            return
        self.measurement_controller.refresh(
            canvas, resolve_scale(self, view), force,
            background=getattr(self, '_drop_batch_background', False))

    def measurements_ready_for_export(self):
        """Wait responsively for complete current results; cancellation aborts export."""
        self.refresh_measurements()
        view = self.get_current_graphics_view()
        if view is None or view.canvas is None:
            return False
        canvas = view.canvas
        state = self.measurement_controller.state(canvas)
        while state.job is not None or getattr(state, 'project', ()):
            QtWidgets.QApplication.processEvents()
            if sip.isdeleted(canvas) or self.get_current_graphics_view() is not view or view.canvas is not canvas:
                return False
            time.sleep(.001)
        return self.measurement_controller.ready(canvas)

    def schedule_measurement_refresh(self):
        if getattr(self, '_defer_batch_refresh', False):
            return
        if not hasattr(self, '_measurement_timer'):
            self._measurement_timer = QTimer(self)
            self._measurement_timer.setSingleShot(True)
            self._measurement_timer.timeout.connect(self.refresh_measurements)
        self._measurement_timer.start(75)

    ### GETMER按钮-可以获得多边形的最小外接矩形MER，
    ### 主要使用了shape中定义的calculate_minimum_rotated_rectangle方法
    ### GETMER Button - It can obtain the minimum enclosing rectangle of a polygon MER.
    ### It mainly utilizes the calculate_minimum_rotated_rectangle method defined in the shape module.
    def _collect_shape_batch(self, canvas, title, calculate, minimum=256):
        """Collect results while pumping Qt; publish only after an uncancelled scan."""
        shapes = list(canvas.shapes)
        progress = None
        if len(shapes) >= minimum:
            progress = QProgressDialog(title, 'Cancel', 0, len(shapes), self)
            progress.setWindowModality(Qt.WindowModal)
            progress.setMinimumDuration(0)
            progress.setAutoClose(False)
            progress.show()
        tab = self.tabWidget.currentWidget()
        values = []
        try:
            for index, shape in enumerate(shapes):
                if progress is not None and index % 32 == 0:
                    progress.setValue(index)
                    QApplication.processEvents()
                    if (progress.wasCanceled() or sip.isdeleted(canvas)
                            or self.tabWidget.indexOf(tab) < 0
                            or tab.property('graphics_view').canvas is not canvas
                            or self.tabWidget.currentWidget() is not tab):
                        return None
                values.append(calculate(shape))
            if progress is not None:
                QApplication.processEvents()
                if progress.wasCanceled():
                    return None
            return values
        finally:
            if progress is not None:
                progress.close()
                progress.deleteLater()

    def Get_MER_on_Canvas(self):
        # 目前仅有长宽的测定
        view = self.get_current_graphics_view()
        if view is None or view.canvas is None:
            return
        canvas = view.canvas
        has_rotated_rect = any(s.shape_type == "rotated_rectangle" for s in canvas.shapes)
        has_polygon = any(s.shape_type == "polygon" for s in canvas.shapes)
        
        if has_rotated_rect and has_polygon:
            reply = QMessageBox.question(
                self,
                "Confirmation",
                "There are already rotated_rectangles on the image. Do you want to continue generating?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No
            )
            if reply == QMessageBox.No:
                return  # 用户选择不继续
            

        prepared = self._collect_shape_batch(
            canvas, 'Generating MER...',
            lambda shape: shape.calculate_minimum_rotated_rectangle(
                minimum_rectangle_size(canvas.image_size.width(), canvas.image_size.height()))
            if shape.visible and shape.shape_type == 'polygon' else None, 64)
        if prepared is None:
            return
        new_shapes = [shape for shape in prepared if shape is not None]
        # 将新形状添加到 canvas.shapes 中
        if not new_shapes:
            return
        canvas.save_state()
        canvas.shapes.extend(new_shapes)
        # 更新形状列表和画布
            # 临时保存并清除选中状态
        temp_selected = canvas.selected_shape.copy() if canvas.selected_shape else []
        canvas.selected_shape = []
        self.update_shapes_and_label_list()
        self.update_canvas()
        canvas.selected_shape = temp_selected
        canvas.shapesChanged.emit()
        self.actionGetMER.setEnabled(False)


    ### 功能实现--绘制形状的ID
    ### Function - Show ID for Drawing Shapes
    def draw_group_id(self):
        current_shapes = self.get_current_shapes()
        if not current_shapes:
            QMessageBox.warning(self, "Notice", "No shapes to show.")
            return

        canvas = self.get_current_graphics_view().canvas
        if self._collect_shape_batch(canvas, 'Updating group IDs...', lambda shape: shape, 512) is None:
            return
        # 切换全局状态
        self._global_show_group_id = not self._global_show_group_id

        # 同步所有形状的显示状态
        for shape in current_shapes:
            if self._global_show_group_id:
                shape.show_group_id()
            else:
                shape.hide_group_id()

        # 更新画布，确保所有形状都被刷新
        self.update_canvas()

    ### 功能实现--将当前所有形状转换为点进行显示
    ### Function - Convert all current shapes into points for display
    def show_points(self):
        # 先检查是否有当前图形视图
        current_graphics_view = self.get_current_graphics_view()
        if not current_graphics_view:
            QMessageBox.warning(self, "Notice", "No images be opened.")
            return

        # 然后检查画布是否存在
        current_canvas = current_graphics_view.canvas
        if not current_canvas:
            QMessageBox.warning(self, "Notice", "Canvas not initialized.")
            return

        # 获取当前形状列表
        current_shapes = self.get_current_shapes()
        if not current_shapes:
            QMessageBox.warning(self, "Notice", "No shapes to show.")
            return

        if not any(shape.visible and shape.shape_type != 'point' for shape in current_shapes):
            return
        prepared = self._collect_shape_batch(
            current_canvas, 'Converting shapes to Points...',
            lambda shape: (shape, shape.get_universe_central_point())
            if shape.visible and shape.shape_type in ('polygon', 'rectangle', 'rotated_rectangle')
            else (shape, None), 64)
        if prepared is None:
            return
        # 标记转换前保存状态
        current_canvas.save_state()

        # 转换可见的形状为点，并正确标记脏状态
        shapes_changed = False
        centers = {id(shape): center for shape, center in prepared if center is not None}
        for shape in current_shapes:
            if shape.visible:
                # 记录原始类型
                original_type = shape.shape_type
                if original_type not in ["point"]:  # 避免重复转换点形状
                    if id(shape) in centers:
                        shape.shape_type = 'point'
                        shape.pointslist = [centers[id(shape)]]
                    shape._dirty = True  # 明确标记形状需要重绘
                    shapes_changed = True

        if shapes_changed:
            # 正确设置画布的脏标记
            # 更新画布
            current_canvas.update()
            # 通知变化
            current_canvas.shapesChanged.emit()
            self.update_shapes_and_label_list()
            self.update_actions_inDocks()

    ### 功能实现--撤销上一次操作
    ### Function  - Reversing the Last Operation
    def undo(self):
        """撤销上一次操作，增加错误检查"""
        if isinstance(QApplication.focusWidget(), (QLineEdit, QtWidgets.QTextEdit, QtWidgets.QPlainTextEdit)):
            QApplication.focusWidget().undo()
            return
        try:
            # 检查是否有当前图形视图
            current_graphics_view = self.get_current_graphics_view()
            if not current_graphics_view:
                QMessageBox.warning(self, "Error", "There is no currently open image. Please open an image first.")
                return
            
            # 检查是否有画布
            canvas = current_graphics_view.canvas
            if not canvas:
                QMessageBox.warning(self, "Error", "The current image has no canvas and thus cannot undo the operation.")
                return
            
            # 检查撤销栈是否为空
            canvas._finish_geometry_edit()
            if not canvas.undo_stack:
                QMessageBox.warning(self, "Notice", "There is no reversible operation.")
                return
                
            # 执行撤销操作
            canvas.undo()
            self.update_undo_button()
        except Exception as e:
            QMessageBox.warning(self, "Error", f"An error occurred during the cancellation operation: {str(e)}")
    def _history_icon(self, redo):
        """Matching vector-style arrows; QIcon/QStyle provide the disabled appearance."""
        icon = QtGui.QIcon()
        for size in (16,24,32,48,64):
            pixmap = QtGui.QPixmap(size,size)
            pixmap.fill(Qt.transparent)
            painter = QtGui.QPainter(pixmap)
            painter.setRenderHint(QtGui.QPainter.Antialiasing)
            painter.scale(size/24,size/24)
            if redo:
                painter.translate(24,0)
                painter.scale(-1,1)
            painter.setPen(QtGui.QPen(self.palette().color(QtGui.QPalette.WindowText),
                                     2.2,Qt.SolidLine,Qt.RoundCap,Qt.RoundJoin))
            path = QtGui.QPainterPath(QtCore.QPointF(5,8))
            path.lineTo(14,8)
            path.cubicTo(23,8,23,20,13,20)
            painter.drawPath(path)
            painter.drawPolyline(QtGui.QPolygonF([QtCore.QPointF(10,3),QtCore.QPointF(5,8),QtCore.QPointF(10,13)]))
            painter.end()
            icon.addPixmap(pixmap)
        return icon

    def redo(self):
        # Text editors own text history; the new shortcut must not edit annotations.
        if isinstance(QApplication.focusWidget(), (QLineEdit, QtWidgets.QTextEdit, QtWidgets.QPlainTextEdit)):
            QApplication.focusWidget().redo()
            return
        view = self.get_current_graphics_view()
        if view and view.canvas:
            view.canvas.redo()
            self.update_undo_button()

    def update_undo_button(self):
        """更新撤销按钮的状态，增加对空画布的检查"""
        current_graphics_view = self.get_current_graphics_view()
        self.actionRedo.setEnabled(bool(current_graphics_view and current_graphics_view.canvas
                                       and current_graphics_view.canvas.redo_stack))
        
        # 检查是否有有效的图形视图
        if current_graphics_view is None:
            # 没有打开标签页，禁用撤销按钮
            self.actionUndo.setEnabled(False)
            self.actionRedo.setEnabled(False)
            self.update_list_on_tab_changed(self.tabWidget.currentIndex())
            return
        
        # 检查是否有有效的画布
        canvas = current_graphics_view.canvas
        if canvas is None:
            self.actionUndo.setEnabled(False)
            self.actionRedo.setEnabled(False)
            self.update_list_on_tab_changed(self.tabWidget.currentIndex())
            return
        
        # 检查撤销栈是否有内容
        if hasattr(canvas, 'undo_stack') and canvas.undo_stack:
            self.actionUndo.setEnabled(True)
        else:
            self.actionUndo.setEnabled(False)

    ### 功能实现--对一个形状进行复制
    ### Function - Copying a Shape
    def duplicate_shape(self):
        """复制选中的形状，保持classnum一致，递增group_id"""
        view = self.get_current_graphics_view()
        if view is None or view.canvas is None:
            return
        canvas = view.canvas
        if not canvas.selected_shape:
            return

        # 获取当前最大的group_id
        existing_shapes = self.get_current_shapes()
        max_group_id = max([s.group_id for s in existing_shapes if s.group_id is not None], default=-1)

        canvas.save_state()
        blocker = QtCore.QSignalBlocker(canvas)
        try:
            # 复制每个选中的形状
            for shape in list(canvas.selected_shape):
                new_shape = shape.copy()  # 使用Shape类的自定义copy方法
                new_shape.selected = False
                # 递增group_id
                max_group_id += 1
                new_shape.group_id = max_group_id
                # 稍微偏移位置以区分
                new_shape.moveBy(10, 10)
                if new_shape.shape_type == 'point' and len(new_shape.pointslist) == 1:
                    new_shape.pointslist = [canvas.bounded_point(new_shape.pointslist[0])]
                # 添加到画布
                canvas.add_shape(new_shape)  # 使用add_shape方法
                new_shape.update_shape()
        finally:
            del blocker
        canvas.shapesChanged.emit()

        # 更新界面
        self.update_actions_inDocks()

    #################################################################
    #canvas和dock窗口的交互，以及刷新功能实现
    #Interaction between the canvas and dock windows, as well as the implementation of the refresh function
    #↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓
    #################################################################
    # 功能实现--labellist 窗口列可见性，在图中显示
    # Function  - Visibility of column labels in the labellist window, displayed in the diagram.
    def on_label_visibility_changed(self, label, visible):
        view = self.get_current_graphics_view()
        if view is None or view.canvas is None:
            return
        canvas = view.canvas
        previous = any(shape.visible for shape in canvas.shapes if shape.label == label)
        shapes = self._collect_shape_batch(canvas, 'Updating class visibility...',
                                           lambda shape: shape, 512)
        if shapes is None:
            self.labeldockinstance.checkbox_dict[label] = previous
            table = self.labeldockinstance.table_widget
            for row in range(table.rowCount()):
                item = table.item(row, 1)
                if item is not None and item.data(Qt.UserRole) == label:
                    checkbox = table.cellWidget(row, 0)
                    blocker = QtCore.QSignalBlocker(checkbox)
                    checkbox.setChecked(previous)
                    del blocker
                    break
            return
        if any(shape.label == label and shape.visible != visible for shape in shapes):
            canvas.save_state()
        else:
            return
        for shape in shapes:
            if shape.label == label:
                shape.visible = visible
        self.shapedockinstance.update_visibility()
        self.get_current_graphics_view().update()
        canvas.shapesChanged.emit()

    # 当在窗口列选择，在Canvas中显示
    # When selecting in the window column, it will be displayed in the Canvas.
        self.schedule_measurement_refresh()

    def _sync_shape_selection(self, shapes, source=None, primary=None, scroll=False):
        if getattr(self, '_syncing_shape_selection', False):
            return
        view = self.get_current_graphics_view()
        canvas = view.canvas if view else None
        if canvas is None or (isinstance(source, Canvas) and source is not canvas):
            return
        if any(canvas._shape_by_id.get(getattr(s, '_history_id', None)) is not s for s in shapes):
            return
        selected = [s for s in shapes if canvas._shape_by_id.get(getattr(s, '_history_id', None)) is s]
        if primary is not None and canvas._shape_by_id.get(getattr(primary, '_history_id', None)) is not primary:
            return
        if primary is None:
            previous = canvas._shape_by_id.get(getattr(self, '_selection_primary_id', None))
            primary = previous if any(s is previous for s in selected) else (selected[-1] if selected else None)
        self._selection_primary_id = getattr(primary, '_history_id', None)
        self._syncing_shape_selection = True
        try:
            canvas.set_selected_shapes(selected)
            # Preserve Qt's current index and Shift anchor in the originating
            # view. Only recipient views select/scroll, once per user gesture.
            if source is not self.shapedockinstance:
                self.shapedockinstance.select_shapes(selected, primary, scroll)
            if source is not self.measured_results_dock:
                self.measured_results_dock.select_shapes(selected, primary, scroll)
            self.actionDuplicate.setEnabled(bool(selected))
            self.actionDelete.setEnabled(bool(selected))
        finally:
            self._syncing_shape_selection = False

    def on_shape_selected_in_dock(self, shapes):
        source = self.sender()
        if source not in (self.shapedockinstance, self.measured_results_dock):
            source = None
        primary = source.primary_shape() if source is not None else None
        self._sync_shape_selection(shapes, source, primary, scroll=True)

    def on_shape_selected_in_canvas(self, shapes):
        sender = self.sender()
        self._sync_shape_selection(shapes, sender if isinstance(sender, Canvas) else None,
                                   shapes[-1] if shapes else None, scroll=True)

    def update_actions_inDocks(self):
        """更加安全地更新dock窗口中的操作状态"""
        try:
            # 更新ShapeListDock
            if hasattr(self, 'shapedockinstance'):
                self.shapedockinstance.table_widget.viewport().update()

            # 更新LabelListDock
            if hasattr(self, 'labeldockinstance'):
                self.labeldockinstance.table_widget.viewport().update()

            # 获取当前画布前进行检查
            current_graphics_view = self.get_current_graphics_view()
            if not current_graphics_view:
                return
                
            # 检查画布是否存在    
            current_canvas = current_graphics_view.canvas
            if not current_canvas:
                return
                
            # 更新工具栏状态
            self.update_actions_inToolBar()

            # [核心优化点：切断信号雪崩]
            # 之前这里发射了 shapesChanged 信号，导致每次新建点都会触发 populate 全量清空并重建几百行表格！
            # 现在注释掉，因为 on_shape_created 里已经调用了增量添加单行的 add_shape()
            # current_canvas.shapesChanged.emit() 
            
            # [DEBUG 验证打印]
            print("[DEBUG - 优化验证] update_actions_inDocks 已执行。成功拦截了全量刷新雪崩！")
            
        except Exception as e:
            print(f"Error in update_actions_inDocks: {e}")

    # 如果标签页改变，更新缩放标签，更新形状列表和标签列表
    def on_tab_changed_and_update_zoom_and_list(self, index):
        if getattr(self, '_defer_batch_refresh', False):
            return
        """标签页变化时的处理，确保安全处理特殊情况"""
        # 检查索引是否有效（有可能是 -1，表示没有标签页）
        if index < 0 or index >= self.tabWidget.count():
            # 没有标签页，禁用相关操作
            self.actionUndo.setEnabled(False)
            self.actionRedo.setEnabled(False)
            return
            
        # 原有的更新缩放和列表
        self.update_zoom_on_tab_change(index)
        self.update_list_on_tab_changed(index)
        self.refresh_measurements()
        
        # 更新 undo 按钮状态
        self.update_undo_button()

        # 更新shapedockinstance与labeldockinstance窗口
    def update_list_on_tab_changed(self, index):
        view = self.get_current_graphics_view()
        canvas = view.canvas if view else None
        shapes = canvas.shapes if canvas is not None else []
        table = self.shapedockinstance.table_widget
        blocker = QtCore.QSignalBlocker(table)
        self.shapedockinstance.populate(shapes)
        self.labeldockinstance.populate(shapes, Shape.get_color_by_classnum)
        del blocker
        self.measurement_controller.bind(canvas)
        if canvas is not None:
            if not getattr(self.tabWidget, '_preserve_navigation_state', False):
                canvas.set_selected_shapes([])
            self._sync_shape_selection(canvas.selected_shape)
        has_shapes = bool(shapes)
        self.actionEditShapes.setChecked(has_shapes)
        self.actionFilterAllEdges.setEnabled(has_shapes)
        self.actionFilterTopLeft.setEnabled(has_shapes)
        self.actionFilterRightBottom.setEnabled(has_shapes)
        self.actionDeleteAllShapes.setEnabled(has_shapes)
        self.actionGetMER.setEnabled(any(s.shape_type == 'polygon' for s in shapes))
        self.refresh_measurements()

    def update_canvas(self):
        """安全地更新当前画布"""
        try:
            # 获取当前图像视图
            graphics_view = self.get_current_graphics_view()
            if not graphics_view:
                return
                
            # 检查画布是否存在
            canvas = graphics_view.canvas
            if not canvas:
                return
                
            # 更新所有形状的可见性
            for shape in canvas.shapes:
                shape.visible = shape.visible  # 保持形状的当前可见性状态
                
            # 请求重绘
            canvas.update()
            self.schedule_measurement_refresh()
        except Exception as e:
            print(f"Error in update_canvas: {e}")

    def on_shapes_changed_in_canvas(self):
        if (getattr(self, '_defer_batch_refresh', False)
                or getattr(self, '_metadata_edit_in_progress', False)):
            return
        view = self.get_current_graphics_view()
        sender = self.sender()
        if isinstance(sender, Canvas) and (not view or sender is not view.canvas):
            return
        self.update_shapes_and_label_list()
        self.refresh_measurements()
        if view and view.canvas:
            self._sync_shape_selection(view.canvas.selected_shape)
        self.update_undo_button()
        # self.update_filter_actions()

    def update_shapes_and_label_list(self):
        if getattr(self, '_defer_batch_refresh', False):
            return
        """安全地更新形状和标签列表"""
        try:
            # 获取当前图像视图
            current_graphics_view = self.get_current_graphics_view()
            if not current_graphics_view:
                # 无需显示消息框，只需要安静地退出
                return
                
            # 检查画布是否存在
            canvas = current_graphics_view.canvas
            if not canvas:
                return
                
            shapes = canvas.shapes
            self.shapedockinstance.sync_shapes(shapes)
            self.labeldockinstance.sync_labels(shapes, Shape.get_color_by_classnum)

        except Exception as e:
            print(f"Error in update_shapes_and_label_list: {e}")

    # 根据选中状态更新按钮的可用性 Update the availability of buttons based on the selected state
    def update_actions_inToolBar(self):
        """安全地根据选中状态更新按钮的可用性"""
        try:
            # 获取当前图形视图
            current_graphics_view = self.get_current_graphics_view()
            if not current_graphics_view:
                # 如果没有当前图形视图，禁用所有相关按钮
                self.actionDuplicate.setEnabled(False)
                self.actionDelete.setEnabled(False)
                return
                
            # 检查画布是否存在
            canvas = current_graphics_view.canvas
            if not canvas:
                self.actionDuplicate.setEnabled(False)
                self.actionDelete.setEnabled(False)
                return
                
            # 根据是否有选中的形状更新按钮状态
            has_selected = bool(canvas.selected_shape)
            self.actionDuplicate.setEnabled(has_selected)
            self.actionDelete.setEnabled(has_selected)
            
        except Exception as e:
            print(f"Error in update_actions_inToolBar: {e}")
            # 出错时禁用所有相关按钮
            self.actionDuplicate.setEnabled(False)
            self.actionDelete.setEnabled(False)

    #################################################################
    # ↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑
    # canvas和dock窗口的交互，以及刷新功能实现
    # Interaction between the canvas and dock windows, as well as the implementation of the refresh function
    #################################################################

    #################################################################
    # 获取当前canvas的所有形状返回一个shape列表与获取当前的图形视图
    # Obtain all shapes of the current canvas and return them as a list of shapes
    # and Get the current graphics view
    #↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓
    #################################################################
    def get_current_shapes(self):
        current_view = self.get_current_graphics_view()
        if current_view and current_view.canvas:
            return current_view.canvas.shapes
        return []


    def get_current_graphics_view(self):
        current_widget = self.tabWidget.currentWidget()
        if current_widget:
            return current_widget.findChild(ImageGraphicsView)
        return None
    #################################################################
    # ↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑
    # 获取当前canvas的所有形状返回一个shape列表与获取当前的图形视图
    # Obtain all shapes of the current canvas and return them as a list of shapes
    # and Get the current graphics view
    #################################################################

    #################################################################
    # 处理缩放问题，与鼠标位置所对应的像素
    # Handling scaling, corresponding pixels to the mouse position
    # ↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓
    #################################################################
    def handle_zoom_changed(self, value):
        """Update controls without feeding rounded percentages into geometry."""
        current_view = self.get_current_graphics_view()
        sender = self.sender()
        if isinstance(sender, ImageGraphicsView) and sender is not current_view:
            return
        self.zoomLineEdit.blockSignals(True)
        self.zoomLineEdit.setText(f"{int(value)}%")
        self.zoomLineEdit.blockSignals(False)
        self.zoomSlider.blockSignals(True)
        self.zoomSlider.setValue(int(value))
        self.zoomSlider.blockSignals(False)
        if current_view:
            current_view.sync_annotation_scale()


    def update_image_status(self, index=None):
        """Image metadata is refreshed on navigation/open/close, never on mouse movement."""
        tab = self.tabWidget.currentWidget() if index is None else self.tabWidget.widget(index)
        view = tab.property('graphics_view') if tab is not None else None
        self.update_scale_status()
        if view is not None and not view.viewport().property('sqStatusFilter'):
            view.viewport().installEventFilter(self)
            view.viewport().setProperty('sqStatusFilter', True)
        if view is not None:
            view.setAcceptDrops(True)
            view.viewport().setAcceptDrops(True)
            view._drop_tab = tab
            view.viewport()._drop_tab = tab
        pixmap = view.pixmap_item.pixmap() if view and view.pixmap_item else None
        has_image = pixmap is not None and not pixmap.isNull()
        self.mousePositionLabel.setText('X: —  Y: —')
        self.pixelValueLabel.setText('Pixel: —')
        self.zoomOutButton.setEnabled(has_image)
        self.zoomInButton.setEnabled(has_image)
        self.imageSizeLabel.setText(f'{pixmap.width()} × {pixmap.height()} px'
                                    if has_image else '— × — px')
        self.fileSizeLabel.setText('— MB')
        file_path = tab.property('file_path') if tab is not None else None
        self.pathLabel.setText(os.path.abspath(os.fspath(file_path)) if has_image and file_path else '')
        if has_image and file_path:
            try:
                size = os.path.getsize(file_path)
                self.fileSizeLabel.setText(f'{size / (1024 * 1024):.1f} MB')
            except OSError:
                pass

    def update_scale_status(self):
        """Display the current tab's effective calibration without resetting pointer status."""
        view = self.get_current_graphics_view()
        info = resolve_scale(self, view) if view is not None else None
        if info is None:
            self.scaleLabel.setText('Scale: Not set')
        else:
            unit = 'µm' if info['unit'] in ('um', 'μm', 'µm') else info['unit']
            unit = 'px' if unit in ('pixel', 'pixels') else unit
            self.scaleLabel.setText(f'Scale: {info["scale"]:.9g} {unit}/px')

    def update_model_status(self):
        """Reflect the loaded global model, independent of image tabs."""
        model = getattr(self, 'model', None)
        name = None
        if model is not None:
            for attribute in ('_stomataquant_source_path', 'model_name', 'ckpt_path'):
                value = getattr(model, attribute, None)
                if isinstance(value, (str, os.PathLike)) and value:
                    name = os.path.basename(os.fspath(value).replace('\\', '/'))
                    break
        self.modelLabel.setModelText(f'Model: {name or ("Unknown" if model is not None else "None")}')

    def eventFilter(self, watched, event):
        if event.type() in (QtCore.QEvent.DragEnter, QtCore.QEvent.DragMove, QtCore.QEvent.Drop):
            if event.mimeData().hasUrls() and any(url.isLocalFile() for url in event.mimeData().urls()):
                event.acceptProposedAction()
                if event.type() == QtCore.QEvent.Drop:
                    from drop_workflow import start_drop
                    start_drop(self, [url.toLocalFile() for url in event.mimeData().urls()
                                      if url.isLocalFile()], getattr(watched, '_drop_tab', None))
                return True
        if event.type() == QtCore.QEvent.Leave:
            view = self.get_current_graphics_view()
            if view is not None and watched is view.viewport():
                self.mousePositionLabel.setText('X: —  Y: —')
                self.pixelValueLabel.setText('Pixel: —')
        return super().eventFilter(watched, event)

    # 对应GUI上鼠标位置标签的改变对于鼠标位置改变时候，更新QLabel
    # Corresponding to the change of the mouse position label on the GUI, update QLabel when the mouse position changes.
    def update_mouse_position(self, x, y):
        try:
            current_graphics_view = self.get_current_graphics_view()
            sender = self.sender()
            if isinstance(sender, ImageGraphicsView) and sender is not current_graphics_view:
                return
            if current_graphics_view and current_graphics_view.pixmap_item:
                pixmap = current_graphics_view.pixmap_item.pixmap()
                if not pixmap.isNull():
                    if 0 <= x < pixmap.width() and 0 <= y < pixmap.height():
                        # 鼠标在图像范围内
                        self.mousePositionLabel.setText(f"X: {x}  Y: {y}")
                    else:
                        # 鼠标在图像范围外
                        self.mousePositionLabel.setText("X: —  Y: —")
                        self.pixelValueLabel.setText("Pixel: —")
                else:
                    self.mousePositionLabel.setText("X: —  Y: —")
                    self.pixelValueLabel.setText("Pixel: —")
            else:
                self.mousePositionLabel.setText("X: —  Y: —")
                self.pixelValueLabel.setText("Pixel: —")
        except Exception as e:
            print(f"Error in update_mouse_position: {e}")

    # 对应GUI上像素值标签的改变对于像素值改变时候，更新QLabel
    # When the pixel value changes, update the QLabel corresponding to the change of the pixel value label on the GUI.
    def update_pixel_value(self, r, g, b):
        try:
            view = self.get_current_graphics_view()
            sender = self.sender()
            if isinstance(sender, ImageGraphicsView) and sender is not view:
                return
            if ((r == -1 and g == -1 and b == -1) or not view or not view.pixmap_item
                    or view.pixmap_item.pixmap().isNull()):
                # 当接收到 -1，表示鼠标在图像范围外，显示 "N/A"
                self.pixelValueLabel.setText("Pixel: —")
            else:
                self.pixelValueLabel.setText(f"Pixel: R={r} G={g} B={b}")
        except Exception as e:
            print(f"Error in update_pixel_value: {e}")

            # 功能：链接Fit to View 按钮:充满界面-

    def fit_to_view(self):
        try:
            current_graphics_view = self.get_current_graphics_view()
            current_graphics_view.fit_to_view_custom()
        except Exception as e:
            QMessageBox.warning(self, "Error", "Currently no image is open, please open an image first.")
            self.createToolButton.setChecked(False)

    # 功能：链接Original Size 按钮:重置缩放-
    # Function: Link "Original Size" button: Reset zooming -
    def reset_zoom(self):
        try:
            current_graphics_view = self.get_current_graphics_view()
            current_graphics_view.resetTransform()
            current_graphics_view.current_zoom = 100
            current_graphics_view.zoomChanged.emit(100)
            # 更新 QLineEdit
            self.zoomLineEdit.setText("100%")
            self.zoomSlider.setValue(100)
        except Exception as e:
            QMessageBox.warning(self, "Error", "Currently no image is open, please open an image first.")
            self.createToolButton.setChecked(False)

    # 功能：连接滑动条的值变化信号到 zoom_slider_changed    缩放改变时候，更新QLineEdit和QSlider
    # Function: Connect the value change signal of the slider to zoom_slider_changed. When zooming is changed, update QLineEdit and QSlider.
    def zoom_slider_changed(self, value):
        current_graphics_view = self.get_current_graphics_view()
        if current_graphics_view:
            current_graphics_view.apply_zoom(value)


    # 功能：链接zoomLineEdit中值发生改变时做的操作；更新QLineEdit和QSlider
    # Function: Link the operation performed when the value in zoomLineEdit changes; Update QLineEdit and QSlider
    def update_zoom_slider(self):
        print("update_zoom_slider 被调用")
        """根据 QLineEdit 的输入更新 zoomSlider 的值。"""
        text = self.zoomLineEdit.text()
        if text.endswith('%'):
            text = text[:-1]
        try:
            value = int(text)
            if 10 <= value <= 1000:
                current_graphics_view = self.get_current_graphics_view()
                if current_graphics_view:
                    current_graphics_view.apply_zoom(value)
                    self.zoomSlider.setValue(value)
                    # if current_graphics_view.canvas:
                    #     current_graphics_view.canvas.set_scale_factor(value / 100.0)
                else:
                    QMessageBox.warning(self, "Invalid scaling", "No graphical views are currently available.")
            else:
                QMessageBox.warning(self, "Invalid scaling value", "The scaling value must be between 10 and 1000.")
        except ValueError:
            QMessageBox.warning(self, "invalid inputs", "Please enter a valid integer.")

    # 更新各个标签和缩放 Update all labels and zoom levels
    def update_zoom_on_tab_change(self, index):
        """
        更新缩放标签的方法，仅在标签页切换时调用。
        """
        current_tab = self.tabWidget.widget(index)
        if current_tab:
            file_path = current_tab.property("file_path")
            graphics_view = current_tab.property("graphics_view")
            print(f"Switch to tag: {file_path}")  # 调试信息
            if file_path and graphics_view and graphics_view.pixmap_item:
                pixmap = graphics_view.pixmap_item.pixmap()
                if not pixmap.isNull():
                    current_zoom = graphics_view.current_zoom
                    self.zoomLineEdit.blockSignals(True)
                    self.zoomLineEdit.setText(f"{int(round(current_zoom))}%")
                    self.zoomLineEdit.blockSignals(False)

                    self.zoomSlider.blockSignals(True)
                    self.zoomSlider.setValue(int(round(current_zoom)))
                    self.zoomSlider.blockSignals(False)

                else:
                    print("Pixmap is null.")
            else:
                print("GraphicsView 或 pixmap_item 不存在，或 file_path 是 None。")
        else:
            print("The current TAB page does not exist。")
        # Batch-created tabs also use this existing UI refresh entry point.
        self.update_image_status()

    #################################################################
    # 一系列形状的创建，主要调用canvas中的方法
    #The creation of a series of shapes
    #↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓
    #################################################################
    ###连接创建polygon,主要调用canvas中的create_polygon方法
    def create_polygon(self):
        try:
            canvas = self.get_current_graphics_view().canvas
            canvas.create_polygon()
        except Exception as e:
            QMessageBox.warning(self, "Error", "Currently no image is open, please open an image first.")
            self.createToolButton.setChecked(False)
    
    ###连接创建rotated_rectangle,主要调用canvas中的create_rotated_rectangle方法
    ###Create a rotated rectangle, mainly by calling the create_rotated_rectangle method in the canvas.
    def create_rotated_rectangle(self):
        try:
            canvas = self.get_current_graphics_view().canvas
            canvas.create_rotated_rectangle()
        except Exception as e:
            QMessageBox.warning(self, "Error", "Currently no image is open, please open an image first.")
            self.createToolButton.setChecked(False)

    ###连接创建rectangle,主要调用canvas中的create_rectangle方法
    ###Create a rectangle, mainly calling the create_rectangle method in the canvas.
    def create_rectangle(self):
        try:
            canvas = self.get_current_graphics_view().canvas
            canvas.create_rectangle()
        except Exception as e:
            QMessageBox.warning(self, "Error", "Currently no image is open, please open an image first.")
            self.createToolButton.setChecked(False)

    ###连接创建line,主要调用canvas中的create_line方法
    ###Create a line, mainly by calling the create_line method in the canvas.
    def create_line(self):
        try:
            canvas = self.get_current_graphics_view().canvas
            canvas.create_line()
        except Exception as e:
            QMessageBox.warning(self, "Error", "Currently no image is open, please open an image first.")
            self.createToolButton.setChecked(False)
 
    ###连接创建point,主要调用canvas中的create_point方法
    ###Create a point, mainly by calling the create_point method within the canvas.
    def create_point(self):
        try:
            canvas = self.get_current_graphics_view().canvas
            canvas.create_point()
        except Exception as e:
            QMessageBox.warning(self, "Error", "Currently no image is open, please open an image first.")
            self.createToolButton.setChecked(False)

    ###每当在 Canvas 类中创建了一个新的形状对象（例如多边形、矩形等），
    ### Canvas 类会发出一个信号 shapeCreated，这个信号连接到 UIMainWindow 类中的 on_shape_created 槽函数。
    ### 该函数负责处理新创建形状的各种属性设置和界面更新，
    ### Whenever a new shape object (e.g., polygon, rectangle, etc.) is created in the Canvas class,
    ### the Canvas class emits a shapeCreated signal, which is connected to the on_shape_created slot function in the UIMainWindow class.
    ### This function is responsible for handling various attribute settings and interface updates for the newly created shape.
    def on_shape_created(self, shape):
        """处理新创建的形状"""
        current_canvas = self.get_current_graphics_view().canvas
        if hasattr(self, '_global_show_group_id') and self._global_show_group_id:
            shape.show_group_id()
        # 检查是否需要自动应用标签
        auto_applied = False
        if current_canvas.apply_label_to_all_shapes:
            label = current_canvas.auto_label
            auto_applied = True
        elif current_canvas.apply_label_to_shape_type and current_canvas.auto_label_shape_type == shape.shape_type:
            label = current_canvas.auto_label
            auto_applied = True
        else:
            # 获取当前所有标签
            existing_shapes = [s for s in self.get_current_shapes() if s is not shape]
            existing_labels = list(set([s.label for s in existing_shapes if s.label]))
            # 显示标签输入对话框
            dialog = LabelInputDialog(existing_labels)
            result = dialog.exec_()

            if result == QDialog.Accepted:
                label = dialog.selected_label
                # 如果用户未输入标签，默认为 None
                if not label:
                    label = None
                current_canvas.auto_label = label
                current_canvas.auto_label_shape_type = shape.shape_type
                current_canvas.apply_label_to_shape_type = dialog.apply_to_shape_type
                current_canvas.apply_label_to_all_shapes = dialog.apply_to_all_shapes
            else:
                # 用户取消，设置标签为 None
                label = None

        # 为形状设置标签
        shape.label = label
# --- 核心性能修复：移除阻塞UI线程的print，优化分配逻辑 ---
        existing_shapes = [s for s in self.get_current_shapes() if s is not shape]
        
        match_classnum = None
        max_group_id = -1
        has_same_type = False
        max_classnum = -1

        for s in existing_shapes:
            # 记录当前最大的 classnum
            if s.classnum is not None and s.classnum > max_classnum:
                max_classnum = s.classnum
                
            if s.label == label:
                if match_classnum is None:
                    match_classnum = s.classnum  # 找到第一个同标签的classnum就记录下来
                
                if s.shape_type == shape.shape_type:
                    has_same_type = True
                    if s.group_id is not None and s.group_id > max_group_id:
                        max_group_id = s.group_id

        if match_classnum is not None:
            # 如果标签已存在，使用相同的属性
            shape.classnum = match_classnum
            if has_same_type:
                shape.group_id = max_group_id + 1
            else:
                # 如果不存在相同 shape_type 的形状，group_id 从 0 开始重新编号
                shape.group_id = 0
        else:
            # 如果是新标签，分配新的 classnum 和 group_id
            shape.classnum = max_classnum + 1
            shape.group_id = 0

        # 更新 UI (这里调用的是单行追加，速度极快)
        self.labeldockinstance.add_label(shape.label)
        self.shapedockinstance.add_shape(shape)
        self.update_actions_inDocks()
        # existing_shapes = [s for s in self.get_current_shapes() if s is not shape]
        # existing_same_label_shapes = []
        # existing_same_type_shapes = []

        # for s in existing_shapes:
        #     if s.label == label:
        #         existing_same_label_shapes.append(s)
        #         # print(f"existing_same_label_shapes: {existing_same_label_shapes}")
        #         print(f"existing_same_type_shapes: {bool(existing_same_label_shapes)}")
        #     if s.label == label and s.shape_type == shape.shape_type:
        #         existing_same_type_shapes.append(s)
        #         # print(f"existing_same_type_shapes: {existing_same_type_shapes}")
        #         print(f"existing_same_type_shapes: {bool(existing_same_type_shapes)}")

        # if existing_same_label_shapes:
        #     # 如果标签已存在，使用相同的属性
        #     shape.classnum = existing_same_label_shapes[0].classnum

        #     if existing_same_type_shapes:
        #         max_group_id = max(s.group_id for s in existing_same_type_shapes)
        #         shape.group_id = max_group_id + 1
        #     else:
        #         # 如果不存在相同 shape_type 的形状，group_id 从 0 开始重新编号
        #         shape.group_id = 0
        # else:
        #     # 如果是新标签，分配新的 classnum 和 group_id
        #     # 获取当前最大的 classnum
        #     max_classnum = -1
        #     for s in existing_shapes:
        #         if s.classnum is not None and s.classnum > max_classnum:
        #             max_classnum = s.classnum
        #         else:
        #             max_classnum = -1
        #     shape.classnum = max_classnum + 1
        #     shape.group_id = 0

        # # 更新 UI
        # self.labeldockinstance.add_label(shape.label)
        # self.shapedockinstance.add_shape(shape)
        # self.update_actions_inDocks()

    #################################################################
    # ↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑
    # 一系列形状的创建，主要调用canvas中的方法
    #The creation of a series of shapes
    #################################################################


    #################################################################
    # 功能实现--打开/关闭文件 Function realization - Open/Close file
    # 打开图形文件，并将其加载到新标签页中的 ImageGraphicsView 组件中。随后，
    # 将 ImageGraphicsView 的 zoomChanged（缩放变化）、mousePositionChanged（鼠标位置变化）和 pixelValueChanged（像素值变化）信号分别连接至对应的处理函数。
    # 同时，将 canvas 的 shapeSelected 信号与 on_shape_selected_in_canvas 槽函数进行绑定，从而确保在画布中选择形状时能够自动触发更新 Dock 表格的操作。
    # Function realization - Open/Close file
    # Open the graphic file and load it into the ImageGraphicsView component in a new tab. Subsequently,
    # Connect the zoomChanged, mousePositionChanged, and pixelValueChanged signals of ImageGraphicsView to the corresponding processing functions respectively.
    # At the same time, bind the shapeSelected signal of the canvas to the on_shape_selected_in_canvas slot function to ensure that the Dock table can be updated automatically when a shape is selected on the canvas.
    #↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓
    #################################################################

    def open_folder(self):
        from drop_workflow import start_drop
        folder = QFileDialog.getExistingDirectory(self, 'Select image folder')
        if not folder:
            return
        return start_drop(self, [folder], folder=True)

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls() and any(url.isLocalFile() for url in event.mimeData().urls()):
            event.acceptProposedAction()
        else:
            super().dragEnterEvent(event)

    def dragMoveEvent(self, event):
        if event.mimeData().hasUrls() and any(url.isLocalFile() for url in event.mimeData().urls()):
            event.acceptProposedAction()
        else:
            super().dragMoveEvent(event)

    def dropEvent(self, event):
        if event.mimeData().hasUrls():
            from drop_workflow import start_drop
            event.acceptProposedAction()
            start_drop(self, [url.toLocalFile() for url in event.mimeData().urls()
                              if url.isLocalFile()])
        else:
            super().dropEvent(event)

    def open_file(self):
        options = QFileDialog.Options()
        file_paths, _ = QFileDialog.getOpenFileNames(self, "Select image files", "",
                                                    "Image Files (*.png *.jpg *.jpeg *.bmp *.tif);;All Files (*)",
                                                    options=options)
        return self.open_image_paths(file_paths)

    def open_image_paths(self, file_paths):
        from batch_ui import image_path_key
        opened = []
        for file_path in file_paths:
            if not file_path:
                continue
            file_path = os.path.abspath(os.fspath(file_path))
            existing = next((i for i in range(self.tabWidget.count())
                             if image_path_key(self.tabWidget.widget(i).property('file_path'))
                             == image_path_key(file_path)), -1)
            if existing < 0:
                print(f"LOAD IMAGE: {file_path} from open_file method")  # 调试信息
                
                # 创建一个新标签页
                tab = QWidget()
                layout = QVBoxLayout(tab)
                
                # 创建ImageGraphicsView实例
                graphics_view = ImageGraphicsView(tab)
                layout.addWidget(graphics_view)
                
                # 尝试加载图像，并检查返回状态
                success, error_msg = graphics_view.load_image(file_path)
                
                if not success:
                    # 显示错误消息并跳过这个文件
                    QMessageBox.warning(
                        self,
                        "Unable to load image",
                        f"Failed to load image file: {file_path}\n\n{error_msg}"
                    )
                    # 销毁已创建的tab和graphics_view
                    tab.deleteLater()
                    continue
                
                # 只有图像成功加载时才继续
                
                # 连接信号和槽
                graphics_view.zoomChanged.connect(self.handle_zoom_changed)
                graphics_view.mousePositionChanged.connect(self.update_mouse_position)
                graphics_view.pixelValueChanged.connect(self.update_pixel_value)
                
                # 设置Canvas信号连接
                graphics_view.canvas.shapeSelected.connect(self.on_shape_selected_in_canvas)
                graphics_view.canvas.shapeCreated.connect(self.on_shape_created)
                graphics_view.canvas.shapesChanged.connect(self.on_shapes_changed_in_canvas)
                
                # 添加标签页
                tab_name = os.path.basename(file_path)
                tab_index = self.tabWidget.addTab(tab, tab_name)
                
                # 设置文件路径和图形视图作为标签页的属性
                tab.setProperty("file_path", file_path)
                tab.setProperty("graphics_view", graphics_view)
                
                # 选择新添加的标签页
                self.tabWidget.setCurrentIndex(tab_index)
                settings = QtCore.QSettings('StomaQuant', 'GUI')
                saved_location = settings.value('annotation_sessions/' + source_suffix(file_path), '')
                saved_session = Path(saved_location) if saved_location and Path(saved_location).exists() else session_path(file_path)
                if saved_session.exists() and not getattr(self, '_suppress_automatic_session_load', False):
                    try:
                        graphics_view.canvas.shapes = load_annotation_session(saved_session, graphics_view.canvas)
                        graphics_view.canvas.shapesChanged.emit()
                    except Exception as error:
                        QMessageBox.warning(self, 'Annotation Session',
                                            f'Could not load saved annotations: {error}')
                tab._annotation_saved_snapshot = annotation_snapshot(graphics_view.canvas)
                tab._annotation_session_path = str(saved_session)
                
                # 将文件添加到已打开文件列表中
                self.opened_files.append(file_path)
                opened.append(tab)
                
                # 启用相关操作
                self.actionEditShapes.setEnabled(True)
                self.actionFilterAllEdges.setEnabled(True)
                self.actionFilterTopLeft.setEnabled(True)
                self.actionFilterRightBottom.setEnabled(True)
                
                self.fit_to_view()
                # The first tab's currentChanged signal precedes setting its properties.
                self.update_image_status()
            else:
                self.tabWidget.setCurrentIndex(existing)
                opened.append(self.tabWidget.widget(existing))
        return opened

    def is_tab_dirty(self, tab):
        view = tab.property('graphics_view') if tab is not None else None
        return bool(view and view.canvas and
                    annotation_snapshot(view.canvas) != getattr(tab, '_annotation_saved_snapshot', ()))

    def _mark_annotation_saved(self, tab):
        view = tab.property('graphics_view') if tab is not None else None
        if view and view.canvas:
            tab._annotation_saved_snapshot = annotation_snapshot(view.canvas)
            saved = session_path(tab.property('file_path'))
            tab._annotation_session_path = str(saved)
            QtCore.QSettings('StomaQuant', 'GUI').setValue(
                'annotation_sessions/' + source_suffix(tab.property('file_path')), str(saved))

    def _save_annotation_session_before_export(self, tab, canvas):
        # YOLO TXT omits labels, IDs, visibility and other annotation kinds.
        # Keep the complete editable state before acknowledging a Save.
        save_annotation_session(session_path(tab.property('file_path')), canvas)

    def _confirm_unsaved_tab(self, tab):
        if self.is_tab_dirty(tab) and not self._discard_unsaved_for_session:
            prompt = QMessageBox(self)
            prompt.setIcon(QMessageBox.Warning)
            prompt.setWindowTitle('Unsaved Annotations')
            prompt.setText('This image has unsaved annotation changes. Save before closing?')
            prompt.setStandardButtons(QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel)
            prompt.setDefaultButton(QMessageBox.Save)
            do_not_ask = QtWidgets.QCheckBox("Don't ask again for this session", prompt)
            prompt.setCheckBox(do_not_ask)
            answer = prompt.exec_()
            if answer == QMessageBox.Cancel or answer not in (QMessageBox.Save, QMessageBox.Discard):
                return False
            if answer == QMessageBox.Discard and do_not_ask.isChecked():
                self._discard_unsaved_for_session = True
            if answer == QMessageBox.Save:
                view = tab.property('graphics_view')
                image_path = tab.property('file_path')
                suggested = getattr(tab, '_annotation_session_path', str(session_path(image_path)))
                destination, _ = QFileDialog.getSaveFileName(
                    self, 'Save Annotations', suggested,
                    'StomataQuant Annotations (*.json);;All Files (*)')
                if not destination:
                    return False
                try:
                    saved = save_annotation_session(destination, view.canvas)
                except Exception as error:
                    QMessageBox.critical(self, 'Save Failed', f'Failed to save annotations: {error}')
                    return False
                tab._annotation_saved_snapshot = saved
                tab._annotation_session_path = destination
                QtCore.QSettings('StomaQuant', 'GUI').setValue(
                    'annotation_sessions/' + source_suffix(image_path), destination)
        return True

    def close_tab(self, index):
        tab = self.tabWidget.widget(index)
        if tab is None or not self._confirm_unsaved_tab(tab):
            return False
        if tab:
            view = tab.property('graphics_view')
            if view and view.canvas:
                if self.measurement_controller.active() is view.canvas:
                    self.shapedockinstance.populate([])
                self.measurement_controller.release(view.canvas)
            task_manager(self).cancel_view(view)
        if tab:
            # 获取文件路径并从打开文件列表中移除
            file_path = tab.property("file_path")
            if file_path in self.opened_files:
                self.opened_files.remove(file_path)  # 移除文件路径
            
            # 获取并清理 graphics_view 对象
            graphics_view = tab.property("graphics_view")
            if graphics_view:
                try:
                    # 断开信号连接
                    graphics_view.zoomChanged.disconnect()
                    graphics_view.mousePositionChanged.disconnect()
                    graphics_view.pixelValueChanged.disconnect()
                    
                    # 清理 Canvas 对象
                    if graphics_view.canvas:
                        # 断开 Canvas 的信号连接
                        graphics_view.canvas.shapeSelected.disconnect()
                        if hasattr(graphics_view.canvas, 'shapesChanged'):
                            graphics_view.canvas.shapesChanged.disconnect()
                        
                        # 明确清空撤销栈，释放资源
                        if hasattr(graphics_view.canvas, 'undo_stack'):
                            graphics_view.canvas._history.clear()
                        graphics_view.canvas.selected_shape = []
                        graphics_view.canvas.hovered_shape = graphics_view.canvas._last_hover_shape = None
                        graphics_view.canvas.current_shape = None
                        graphics_view.canvas._edit_original = ()
                        graphics_view.canvas._edit_before = None
                        graphics_view.canvas._history_pending = None
                        graphics_view.canvas._reset_edit_motion()
                        
                        # 清空 Canvas 的形状列表
                        if hasattr(graphics_view.canvas, 'shapes'):
                            graphics_view.canvas.shapes.clear()
                        
                        # 从场景中移除 Canvas
                        graphics_view.scene().removeItem(graphics_view.canvas)
                        graphics_view.canvas = None
                    
                    # 清理 pixmap_item
                    if graphics_view.pixmap_item:
                        graphics_view.scene().removeItem(graphics_view.pixmap_item)
                        graphics_view.pixmap_item = None
                    
                    # 清空场景
                    graphics_view.scene().clear()
                    
                    # 如果有比例尺信息，也清除它
                    if hasattr(graphics_view, 'scale_info'):
                        graphics_view.scale_info = None
                except Exception as e:
                    print(f"清理资源时出错: {e}")
            
            # 标记要删除的标签页
            tab.setProperty("to_be_deleted", True)
            tab.deleteLater()
            
            # 手动触发垃圾回收
            gc.collect()
        
        # 移除标签页
        self.tabWidget.removeTab(index)
        
        # 更新UI状态，如果没有标签页了，更新所有dock窗口
        if self.tabWidget.count() == 0:
            self.shapedockinstance.populate([])
            self.labeldockinstance.populate([], Shape.get_color_by_classnum)
            self.measured_results_dock.populate([])
            self.image_results_summary_dock.populate([], 0, 0, None)
            
            # 重置状态栏
            self.update_image_status()
            
            # 禁用依赖图像的操作
            self.actionEditShapes.setEnabled(False)
            self.actionGetMER.setEnabled(False)
            self.actionFilterAllEdges.setEnabled(False)
            self.actionFilterTopLeft.setEnabled(False)
            self.actionFilterRightBottom.setEnabled(False)
        return True

    #################################################################
    # ↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑
    # 功能实现--打开/关闭文件 Function realization - Open/Close file
    #################################################################


    #################################################################
    # 推理Ad和Ab分类，调用单独线程
    # Ad and Ab classification, with separate thread
    # ↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓
    #################################################################

    def inference_ABorAD(self):
        try:
            # 显示确认信息框
            reply = QMessageBox.question(
                self,
                "Please confirm:",
                "This function only supports Arabidopsis. Do you want to continue?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No
            )

            if reply == QMessageBox.Yes:
                # 显示进度对话框
                self.progress_dialog_aborad = ProgressDialog(self)
                self.progress_dialog_aborad.show()
                self.progress_dialog_aborad.update_message("Performing AB/AD classification...")

                # 获取当前图像路径
                current_tab = self.tabWidget.currentWidget()
                file_path = current_tab.property("file_path") if current_tab else None

                # 如果没有图像，显示错误
                if not file_path:
                    self.progress_dialog_aborad.accept()
                    QMessageBox.warning(self, "Error", "Currently no image is open, please open an image first.")
                    return

                # 设置模型路径
                # cls_model_path = r"Cls_best.pt"
                # 从资源文件中读取模型

                model_resource = QFile(":/Cls_best.pt")
                if sys.platform == 'darwin' and not model_resource.exists():
                    bundled_model = macos_resource_path('Cls_best.pt')
                    if bundled_model:
                        model_resource = QFile(bundled_model)
                if not model_resource.open(QIODevice.ReadOnly):
                    QMessageBox.critical(self, "错误", "无法从资源加载模型文件")
                    return None
                
                # 创建临时文件
                temp_model = tempfile.NamedTemporaryFile(delete=False, suffix='.pt')
                temp_model_path = temp_model.name
                
                # 写入临时文件
                model_data = model_resource.readAll()
                temp_model.write(model_data.data())
                temp_model.close()
                            # 保存临时文件路径以便后续清理
                self._temp_model_path = temp_model_path
                print(f"Temporary model file has been created: {temp_model_path}")

                # 创建并启动线程
                self.aborad_thread = ABorADInferenceThread(temp_model_path, file_path, self)
                manager = task_manager(self)
                task = manager.begin(current_tab, 'classification', self.progress_dialog_aborad)
                self.aborad_thread.inferenceFinished.connect(
                    lambda ab, ad, path, error, t=task: self.on_aborad_inference_finished(ab, ad, path, error, t))
                self.aborad_thread.finished.connect(lambda p=temp_model_path: self._cleanup_aborad_resources(p))
                manager.start(task, self.aborad_thread)

        except Exception as e:
            if hasattr(self, 'progress_dialog_aborad') and self.progress_dialog_aborad:
                self.progress_dialog_aborad.accept()
            QMessageBox.warning(self, "Error", f"An error occurred: {str(e)}")
            if 'temp_model_path' in locals():
                self._cleanup_aborad_resources(temp_model_path)

    def on_aborad_inference_finished(self, ab_probability, ad_probability, file_path, error, task=None):
        manager = task_manager(self)
        valid = manager.valid(task)
        manager.finish(task)
        if not valid:
            return
        if error:
            QMessageBox.warning(self, 'Error', str(error))
        else:
            QMessageBox.information(self, 'Result:',
                f'{os.path.basename(file_path)}\nabaxial_probability: {ab_probability:.4f}%, adaxial_probability: {ad_probability:.4f}%')

    def _cleanup_aborad_resources(self, path):
        if path and os.path.exists(path):
            os.unlink(path)

    #################################################################
    # ↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑
    # 推理Ad和Ab分类，调用单独线程
    # Ad and Ab classification, with separate thread
    #################################################################

    #################################################################
    # 关于模型推理部分，有模型加载，以及调用单独的线程进行推理
    # # Regarding the model inference part, there are model loading and calling of separate threads for inference.
    # ↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓
    #################################################################

    ### 模型选择函数，对应模型选择按钮 Model selection function, corresponding to the model selection button
    def load_model(self):
        options = QFileDialog.Options()
        model_path, _ = QFileDialog.getOpenFileName(self, "Select the YOLO model file", "",
                                                    "Model Files (*.pt *.onnx);;All Files (*)", options=options)
        if model_path:
            try:
                # 检查是否已经加载了模型，释放旧模型资源
                if hasattr(self, 'model') and self.model is not None:
                    try:
                        del self.model
                        self.model = None
                        gc.collect()
                        print('The old model has been released successfully.')
                    except Exception as e:
                        print(f"An error occurred while releasing the resources of the old model: {e}")

                # 加载新模型
                self.model = YOLO(model_path)
                self.model._stomataquant_source_path = model_path
                self.update_model_status()
                model_name = model_path.split('/')[-1] if '/' in model_path else model_path.split('\\')[-1]
                QMessageBox.information(self, "Model loading success",
                                        f"The model has been successfully loaded: {model_name}")
                print(f"The model has been successfully loaded: {model_path}, {self.model.model_name}")

            except Exception as e:
                QMessageBox.critical(self, "Model loading failure", f"Unable to load model: {str(e)}")
            finally:
                self.update_model_status()

    ### 关于推理设置的函数，其使用了InferenceSettingsDialog类，对应推理设置按钮
    ### Regarding the function for setting up the inference, it utilizes the InferenceSettingsDialog class, which corresponds to the inference settings button.
    def show_inference_settings(self):
        try:
            dialog = InferenceSettingsDialog(self)
            if not self.inference_settings:
                dialog.load_default_settings()
            else:
                dialog.set_settings(self.inference_settings)
                    
            if dialog.exec_() == QDialog.Accepted:
                self.inference_settings = dialog.get_settings()
                print("Inference Settings Updated:", self.inference_settings)  # 调试输出
            else:
                print("Inference Settings Dialog Canceled")  # 调试输出
                dialog.set_settings(self.inference_settings)

        except Exception as e:
            print(f"Error in show_inference_settings: {e}")

    ### 运行YOLO推理函数，对应AI按钮，调用线程进行推理
    ### Run the YOLO inference function, corresponding to the AI button, and call the thread to perform the inference.
    def run_YOLO_seg_inference(self):
        try:
            # 检查是否有打开的图像
            current_tab = self.tabWidget.currentWidget()
            if not current_tab:
                QMessageBox.warning(self, "Error", "Currently no image is open, please open an image first.")
                return

            # 获取图像视图和文件路径
            graphics_view = current_tab.property("graphics_view")
            file_path = current_tab.property("file_path")

            if not graphics_view or not file_path:
                QMessageBox.warning(self, "Error", "Unable to get the image file path or view.")
                return

            # 检查是否已加载模型
            if not self.model:
                QMessageBox.warning(self, "Warning", "Please load a model before inference.")
                return
            
            # 显示进度对话框
            self.progress_dialog = ProgressDialog(self)
            self.progress_dialog.show()
            self.progress_dialog.update_message("Running inference...")

            # 如果推断设置为空，则加载默认值
            if not self.inference_settings:
                self.inference_settings = {
                    "conf": 0.5,
                    "iou": 0.7,
                    "device": "cpu",
                    "save_path": (macos_output_dir("Inference_OutPut") if sys.platform == "darwin"
                                  else os.path.join(os.getcwd(), "Inference_OutPut")),
                    "imgsz": 1024,
                    "max_det": 500
                }
            
            # 创建并启动推理线程
            self.yolo_thread = YOLOSegInferenceThread(self.model, file_path, self.inference_settings, self)
            manager = task_manager(self)
            task = manager.begin(current_tab, 'inference', self.progress_dialog, self.inference_settings)
            self.yolo_thread.inferenceFinished.connect(
                lambda results, path, error, t=task: self.on_inference_finished(results, path, error, t))
            manager.start(task, self.yolo_thread)

        except Exception as e:
            if hasattr(self, 'progress_dialog') and self.progress_dialog:
                self.progress_dialog.accept()
            QMessageBox.critical(self, "Error", f"An error occurred: {str(e)}")
            
    ###  完成推理后的一些任务，json 文件生成，shape 类的生成在推理完成后，以及释放不再使用的变量
    ### Some tasks after completing the inference, such as generating JSON files,
    ### generating Shape classes , and releasing variables that are no longer in use.
    # 修改on_inference_finished函数
    def on_inference_finished(self, results, file_path, error, task=None):
        manager = task_manager(self)
        if not manager.valid(task):
            manager.finish(task)
            return
        try:
            if error:
                raise error if isinstance(error, Exception) else RuntimeError(error)
            output_dir = task.settings.get(
                'save_path', macos_output_dir('Inference_OutPut') if sys.platform == 'darwin'
                else os.path.join(os.getcwd(), 'Inference_OutPut'))
            records, polygons = decode_predictions(results, output_dir)
            if not records:
                manager.finish(task)
                QMessageBox.warning(self, 'Notice', 'The model did not return any inference results.')
                return
            if polygons:
                task.dialog.update_message('Processing polygon data...')
                size = task.canvas.image_size
                worker = PolygonProcessThread(polygons, size.width(), size.height(), records, self)
                worker.processingFinished.connect(
                    lambda processed, items, error, t=task: self.on_polygon_processing_finished(processed, items, error, t))
                manager.start(task, worker)
            else:
                self.finish_processing_shapes(shapes_from_predictions(records, {}, task.canvas), task)
        except Exception as error:
            manager.finish(task)
            if not isinstance(error, OperationCancelled):
                QMessageBox.warning(self, 'Inference error', str(error))


    def on_polygon_processing_finished(self, processed_map, json_obj, error, task=None):
        manager = task_manager(self)
        if not manager.valid(task):
            manager.finish(task)
            return
        try:
            if error:
                raise error if isinstance(error, Exception) else RuntimeError(error)
            output_dir = task.settings.get(
                'save_path', macos_output_dir('Inference_OutPut') if sys.platform == 'darwin'
                else os.path.join(os.getcwd(), 'Inference_OutPut'))
            rejected = save_polygon_audit(processed_map, task.file_path, output_dir)
            shapes = shapes_from_predictions(json_obj, processed_map, task.canvas)
            self.finish_processing_shapes(shapes, task)
            if rejected:
                QMessageBox.warning(self, 'Skipped predictions',
                                    f'{len(rejected)} predicted polygon(s) could not be converted '
                                    'to valid shapes and were skipped. Details are in the postprocess audit.')
        except Exception as error:
            manager.finish(task)
            if not isinstance(error, OperationCancelled):
                QMessageBox.warning(self, 'Polygon processing error', str(error))

    # 添加一个新的辅助方法来完成处理
    def finish_processing_shapes(self, shapes, task=None):
        manager = task_manager(self)
        if not manager.valid(task):
            manager.finish(task)
            return
        canvas = task.canvas
        # Preserve the existing append behavior; no replacement of user annotations.
        canvas.save_state()
        canvas.shapes.extend(shapes)
        canvas.set_mode('edit')
        canvas.update()
        canvas.shapesChanged.emit()
        if self.get_current_graphics_view() is task.view:
            self.actionEditShapes.setChecked(True)
            self.edit_shapes()
            self.update_actions_inToolBar()
        manager.finish(task)

    def closeEvent(self, event):
        if not getattr(self, '_close_tabs_confirmed', False):
            count = self.tabWidget.count()
            if count:
                answer = QMessageBox.question(
                    self, 'Exit StomataQuant',
                    f'You currently have {count} tab{"s" if count != 1 else ""} open.\n'
                    'Some work may not have been saved.\n'
                    'Are you sure you want to exit StomataQuant?',
                    QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
                if answer != QMessageBox.Yes:
                    event.ignore()
                    return
            self._close_tabs_confirmed = True
        manager = task_manager(self)
        batch = getattr(self, '_drop_batch', None)
        if batch is not None and not batch.done:
            batch.cancel()
        self.measurement_controller.cancel_all()
        if (manager.running() or self.measurement_controller.running()
                or getattr(self, '_batch_running', False)
                or (batch is not None and not batch.done)):
            manager.cancel_all()
            self._closing_requested = True
            self.statusBar().showMessage('Waiting for the current processing stage to stop safely...', 5000)
            QTimer.singleShot(100, self.close)
            event.ignore()
            return
        super().closeEvent(event)


    #################################################################
    # ↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑
    # 关于模型推理部分，有模型加载，以及调用单独的线程进行推理
    # # Regarding the model inference part, there are model loading and calling of separate threads for inference.
    #################################################################

    ####################################################################
    # 以下方法与更改显示形状的颜色相关
    # The methods are related to the modification of the color of the shape.
    ####################################################################

    def show_display_settings(self):
        dialog = DisplaySettingsDialog(self, Shape.color_map, display.current)
        if dialog.exec_() == QtWidgets.QDialog.Accepted:
            try:
                self.apply_display_settings(dialog.get_color_map(), dialog.get_appearance())
            except (ValueError, TypeError) as exc:
                QMessageBox.warning(self, "Display Settings", str(exc))

    def apply_display_settings(self, color_map, appearance):
        colors_changed = color_map != Shape.color_map
        views = [self.tabWidget.widget(i).property("graphics_view") for i in range(self.tabWidget.count())]
        canvases = [view.canvas for view in views if getattr(view, 'canvas', None) is not None]
        # Notify Qt before changing the shared bounds. Shapes are painted by Canvas.
        for canvas in canvases:
            canvas.prepareGeometryChange()
            for shape in canvas.shapes + ([canvas.current_shape] if canvas.current_shape else []):
                shape.prepareGeometryChange()
        Shape.set_color_map(color_map)
        display.set_current(appearance)
        settings = QtCore.QSettings("StomaQuant", "GUI")
        for class_num, color in color_map.items():
            settings.setValue(f"colors/class_{class_num}", color)
        display.save(settings, appearance)
        for canvas in canvases:
            for shape in canvas.shapes + ([canvas.current_shape] if canvas.current_shape else []):
                shape.appearance_changed()
            canvas.update()
        for view in views:
            if getattr(view, 'canvas', None) is not None:
                view.viewport().update()
        # Appearance alone does not alter annotation lists, measurements or history.
        if colors_changed:
            self.update_shapes_and_label_list()

    def load_color_settings(self):
        """从 QSettings 加载颜色设置"""
        settings = QtCore.QSettings("StomaQuant", "GUI")
        color_map = dict(Shape.color_map)
        
        # 获取所有颜色设置的键
        settings_keys = settings.allKeys()
        color_keys = [key for key in settings_keys if key.startswith("colors/class_")]
        
        for key in color_keys:
            try:
                class_num = int(key.split("_")[1])
                color_value = settings.value(key)
                
                # 将保存的QColor对象转换回来
                if isinstance(color_value, QtGui.QColor):
                    color = color_value
                else:
                    # 如果不是QColor对象，尝试创建
                    color = QtGui.QColor(color_value)
                    
                if color.isValid():
                    color_map[class_num] = color
            except (IndexError, ValueError, TypeError) as e:
                print(f"Loading color setting error: {e}")
        
        # 如果有颜色设置，则应用它们
        if color_map:
            Shape.set_color_map(color_map)

    ####################################################################
    # 以下方法多边形的特征热图保存功能相关，其调用单独的线程
    # The following method is related to the feature heatmap saving function of polygons, and it calls a separate thread.
    ####################################################################

    def show_heatmap(self):
        """显示热图对话框并根据用户选择生成热图"""
        try:
            target_tab = self.tabWidget.currentWidget()
            # 检查是否有图像和形状
            current_view = self.get_current_graphics_view()
            if not current_view or not current_view.pixmap_item:
                QtWidgets.QMessageBox.warning(self, "Notice", "Please open an image first.")
                return

            # 获取当前可见的多边形形状
            shapes = [s for s in self.get_current_shapes() 
                    if s.visible and s.shape_type == 'polygon']
            
            if not shapes:
                QtWidgets.QMessageBox.warning(self, "Notice", "No polygon shape is available.")
                return

            # 检查是否已提取特征
            has_features = False
            for shape in shapes:
                if hasattr(shape, 'feature_results') and isinstance(shape.feature_results, dict) and shape.feature_results:
                    has_features = True
                    break
            
            if not has_features:
                reply = QtWidgets.QMessageBox.question(
                    self, "Notice",
                    "The shape has not yet extracted the features. Should we extract the features first?",
                    QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
                    QtWidgets.QMessageBox.Yes
                )
                if reply == QtWidgets.QMessageBox.Yes:
                    if not self.measurements_ready_for_export():
                        return
                else:
                    return
            
            # 创建并显示热图对话框
            dialog = HeatMapDialog(self)
            if dialog.exec_() == QtWidgets.QDialog.Accepted:
                if (target_tab is None or sip.isdeleted(target_tab)
                        or self.tabWidget.indexOf(target_tab) < 0
                        or sip.isdeleted(current_view) or not current_view.canvas):
                    return
                shapes = [s for s in current_view.canvas.shapes if s.visible and s.shape_type == 'polygon']
                settings = dialog.get_settings()
                feature_name = settings["feature"]
                colormap_name = settings["colormap"]
                output_path = settings["output_path"]
                scale_info = resolve_scale(self, current_view)
                errors = refresh_shapes(shapes, scale_info, force=True)
                if errors:
                    QMessageBox.warning(self, 'Measurement needs correction', '\n'.join(errors[:10]))
                    return
                
                if not output_path:
                    QtWidgets.QMessageBox.warning(self, "Noticce", "Please select the save path.")
                    return
                
                # 显示进度对话框
                self.progress_dialog_heatmap = ProgressDialog(self)
                self.progress_dialog_heatmap.update_message(f"Generating a heatmap based on {feature_name} is in progress....")
                self.progress_dialog_heatmap.show()
                
                # 获取图像副本
                current_pixmap = current_view.pixmap_item.pixmap()
                image = current_pixmap.toImage()
                file_path = target_tab.property("file_path")
            
                # 创建并启动热图生成线程
                
                # 创建并启动热图生成线程
                self.heatmap_thread = HeatMapGenerationThread(
                    image, shapes, feature_name, colormap_name, output_path, file_path, scale_info, self
                )
                manager = task_manager(self)
                task = manager.begin(target_tab, 'heatmap', self.progress_dialog_heatmap)
                self.heatmap_thread.heatmapGenerated.connect(
                    lambda path, error, t=task: self.on_heatmap_generated(path, error, t))
                manager.start(task, self.heatmap_thread)


        
        except Exception as e:
            import traceback
            print(f"Error occurred when displaying the heatmap dialog box: {str(e)}")
            print(traceback.format_exc())
            QtWidgets.QMessageBox.critical(self, "Error", f"An error occurred while executing the heatmap function：{str(e)}")
            if hasattr(self, 'progress_dialog_heatmap'):
                self.progress_dialog_heatmap.accept()

    def on_heatmap_generated(self, file_path, error, task=None):
        manager = task_manager(self)
        valid = manager.valid(task)
        manager.finish(task)
        if not valid:
            return
        if error:
            QMessageBox.warning(self, 'Error', str(error))
        elif file_path:
            QMessageBox.information(self, 'Saved successfully',
                                    f'The heatmap generation was successful and saved to:\n{file_path}')

    ####################################################################
    # 以下方法多边形/正方形注释的保存或者导入相关
    # Save or Import Polygon/(Rotated) Rectangle Annotation Methods Related to This
    # ↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓
    ####################################################################

    def change_point_class(self, shape, category):
        """Compatibility entry point; metadata changes are shared by all shapes."""
        self.change_shape_metadata([shape], 'classnum', str(category))

    def _queue_metadata_edit(self, shapes, field, text):
        view = self.get_current_graphics_view()
        if view and view.canvas:
            self.metadataCommit.emit((view.canvas, view.canvas._history_generation, list(shapes)), field, text)

    def _apply_metadata_edit(self, context, field, text):
        canvas, generation, shapes = context
        view = self.get_current_graphics_view()
        if view and view.canvas is canvas and canvas._history_generation == generation:
            self.change_shape_metadata(shapes, field, text)

    def change_shape_metadata(self, shapes, field, text):
        """One undoable edit, bound to actual objects in the current image."""
        tab = self.tabWidget.currentWidget()
        if tab is None or field not in ('label', 'classnum') or not shapes:
            return
        canvas = require_target(self, tab)
        current = {id(shape) for shape in canvas.shapes}
        # A queued editor commit may arrive after tab switching, closing or undo.
        if any(id(shape) not in current for shape in shapes):
            return
        targets = list({id(shape): shape for shape in shapes}.values())
        if field == 'classnum':
            from point_annotations import class_id
            try:
                category = class_id(text)
            except ValueError as error:
                QMessageBox.warning(self, 'Invalid class ID', str(error))
                return
            # Preserve the existing current-image lookup, before modifying any
            # selected shape. Table sort order must never determine the mapping.
            label = next((s.label for s in canvas.shapes
                          if s.classnum == category and s.label), f'Class {category}')
            changes = [(s, label, category) for s in targets if s.classnum != category]
        else:
            label = text.strip() or None  # Same convention as LabelInputDialog.
            changes = [(s, label, s.classnum) for s in targets if s.label != label]
        if not changes:
            return
        renames = {shape.label: label for shape, label, _ in changes}
        canvas.save_state()
        for shape, label, category in changes:
            shape.label = label
            shape.classnum = category
            if shape.feature_results:
                shape.feature_results['Label'] = label
            shape.update_shape()
        self.shapedockinstance.update_metadata([s for s, _, _ in changes])
        self.labeldockinstance.sync_labels(canvas.shapes, Shape.get_color_by_classnum, renames)
        canvas.update()
        self._metadata_edit_in_progress = True
        try:
            canvas.shapesChanged.emit()
        finally:
            self._metadata_edit_in_progress = False
        self.update_undo_button()
        self.refresh_measurements()

    def import_point(self):
        tab = self.tabWidget.currentWidget()
        if tab is None:
            QMessageBox.warning(self, 'Notice', 'Please open an image file first.')
            return
        progress = None
        try:
            canvas = require_target(self, tab)
            path, _ = QFileDialog.getOpenFileName(
                self, 'Import Point Annotations', '', 'Text Files (*.txt);;All Files (*)')
            if not path:
                return
            require_target(self, tab, canvas)
            progress = QProgressDialog('Importing Point annotations...', 'Cancel', 0, 0, self)
            progress.setWindowModality(Qt.WindowModal)
            progress.setMinimumDuration(500)
            count = import_points(canvas, path,
                                  lambda: import_checkpoint(self, tab, canvas, progress),
                                  getattr(self, '_global_show_group_id', False))
            refresh_point_import(self, tab)
            progress.close()
            QMessageBox.information(self, 'Import Success', f'Successfully imported {count} Point annotations.')
        except OperationCancelled:
            pass
        except Exception as error:
            QMessageBox.critical(self, 'Error', f'Failed to import Point annotations: {error}')
        finally:
            if progress is not None:
                progress.close()
                progress.deleteLater()

    def save_point_annotation(self):
        tab = self.tabWidget.currentWidget()
        if tab is None:
            QMessageBox.warning(self, 'Notice', 'Please open an image file first.')
            return
        try:
            canvas = require_target(self, tab)
            if not any(shape.shape_type == 'point' and shape.visible for shape in canvas.shapes):
                QMessageBox.warning(self, 'Notice', 'No visible Point annotations to save.')
                return
            stem = os.path.splitext(os.path.basename(tab.property('file_path')))[0]
            path, _ = QFileDialog.getSaveFileName(
                self, 'Export Point Annotations',
                f'Point_Annotation_Exported_by_StomataQuant_{stem}.txt',
                'Text Files (*.txt);;All Files (*)')
            if not path:
                return
            require_target(self, tab, canvas)
            self._save_annotation_session_before_export(tab, canvas)
            write_points(path, canvas)
            self._mark_annotation_saved(tab)
            QMessageBox.information(self, 'Success', 'Point annotations saved successfully!')
        except Exception as error:
            QMessageBox.critical(self, 'Error', f'Failed to save Point annotations: {error}')

    def _require_active_annotation_target(self, tab, canvas=None):
        if (tab is None or sip.isdeleted(tab) or self.tabWidget.currentWidget() is not tab):
            raise ValueError('The target image was closed or changed during import.')
        return require_target(self, tab, canvas)

    def _commit_annotation_import(self, tab, canvas, shapes):
        """Commit a fully parsed import as one undoable, signal-safe operation."""
        if not shapes:
            return False
        self._require_active_annotation_target(tab, canvas)
        canvas.save_state()
        was_blocked = canvas.blockSignals(True)
        try:
            canvas.shapes.extend(shapes)
        finally:
            canvas.blockSignals(was_blocked)
        canvas.update()
        canvas.shapesChanged.emit()
        self.update_shapes_and_label_list()
        return True

    def _import_shape_annotations(self, kind, title):
        current_tab = self.tabWidget.currentWidget()
        if not current_tab:
            QMessageBox.warning(self, "Notice", "Please open an image file first.")
            return
        file_path, _ = QFileDialog.getOpenFileName(
            self, title, "", "Text Files (*.txt);;All Files (*)")
        if not file_path:
            return

        progress = None
        try:
            canvas = self._require_active_annotation_target(current_tab)
            width, height = canvas.image_size.width(), canvas.image_size.height()
            with open(file_path, 'r', encoding='utf-8-sig') as stream:
                lines = stream.readlines()
            require_annotation_text(lines)
            table_header = rectangle_table_header_index(lines) if kind == 'rectangle' else None
            progress = QProgressDialog(f"Importing {kind.replace('_', ' ')} annotations...",
                                       "Cancel", 0, len(lines), self)
            progress.setWindowModality(Qt.WindowModal)
            progress.setMinimumDuration(500)
            pending, skipped, next_ids = [], [], {}
            for number, line in enumerate(lines, 1):
                if progress.wasCanceled():
                    return
                progress.setValue(number - 1)
                QApplication.processEvents()
                self._require_active_annotation_target(current_tab, canvas)
                if not line.strip() or table_header == number - 1:
                    continue
                try:
                    if table_header is not None:
                        category, points, label = parse_rectangle_table_line(line, width, height)
                    else:
                        category, points = parse_annotation_line(line, kind, width, height)
                        label = f"Class {category}"
                except (ValueError, IndexError, OverflowError) as error:
                    skipped.append((number, str(error)))
                    continue
                if category not in next_ids:
                    ids = [shape.group_id for shape in canvas.shapes
                           if shape.classnum == category and shape.group_id is not None]
                    next_ids[category] = max([-1, *ids]) + 1
                pending.append(Shape(label=label, classnum=category,
                                     pointslist=points, shape_type=kind,
                                     group_id=next_ids[category]))
                next_ids[category] += 1
            progress.setValue(len(lines))
            if progress.wasCanceled():
                return
            self._commit_annotation_import(current_tab, canvas, pending)
            warning = import_warning(skipped, len(pending))
            if warning:
                QMessageBox.warning(self, 'Annotation Import Warning', warning)
            elif pending:
                QMessageBox.information(self, "Import Success",
                                        f"Successfully imported {len(pending)} {kind.replace('_', ' ')} annotations")
            else:
                QMessageBox.warning(self, "Warning", f"No {kind.replace('_', ' ')} annotations were imported.")
        except Exception as error:
            QMessageBox.critical(self, "Error",
                                 f"An error occurred when importing the annotation file: {error}")
        finally:
            if progress is not None:
                progress.close()
                progress.deleteLater()

    def import_polygon(self):
        self._import_shape_annotations('polygon', 'Import Annotation File')

    def import_rectangle(self):
        self._import_shape_annotations('rectangle', 'Import Rectangle Annotation File')

    def import_rotated_rectangle(self):
        self._import_shape_annotations('rotated_rectangle', 'Import Rotated Rectangle Annotation')

    def save_polygon_annotation(self):
        current_shapes = self.get_current_shapes()
        if not current_shapes:
            QMessageBox.warning(self, "Notice", "No shapes to save.")
            return

        # 检查是否有polygon类型的形状
        has_polygon = False
        for shape in current_shapes:
            if shape.shape_type == 'polygon' and shape.visible:
                has_polygon = True
                break

        if not has_polygon:
            QMessageBox.warning(self, "Notice", "No visible polygon annotations to save.")
            return

        # 获取当前文件名作为默认保存文件名的一部分
        current_tab = self.tabWidget.currentWidget()
        default_filename = "Polygon_Annotation_Exported_by_StomataQuant"
        if current_tab:
            file_path_original = current_tab.property("file_path")
            if file_path_original:
                file_name_without_ext = os.path.splitext(os.path.basename(file_path_original))[0]
                default_filename = f"Polygon_Annotation_Exported_by_StomataQuant_{file_name_without_ext}.txt"

        # 弹出文件保存对话框，使用默认文件名
        file_path, _ = QFileDialog.getSaveFileName(self,
                                                   "Save YOLO Annotation", default_filename,
                                                   "Text Files (*.txt);;All Files (*)")

        if not file_path:
            return

        try:
            canvas = self._require_active_annotation_target(current_tab)
            with io.StringIO() as f:
                for shape in current_shapes:
                    # 只处理polygon类型
                    if shape.shape_type != 'polygon' or not shape.visible:
                        continue
                    # YOLO格式:类别编号 x1 y1 x2 y2 x3 y3...
                    points = []
                    # 添加类别编号
                    points.append(str(shape.classnum))
                    # 获取图片尺寸用于归一化坐标
                    current_canvas = canvas
                    image_size = current_canvas.image_size
                    image_width = image_size.width()
                    image_height = image_size.height()
                    # 添加归一化后的坐标点
                    for point in shape.pointslist:
                        x = point.x() / image_width
                        y = point.y() / image_height
                        points.extend([f"{x:.6f}", f"{y:.6f}"])
                    # 写入一行
                    line = ' '.join(points) + '\n'
                    try:
                        validate_polygon_export(line, image_width, image_height, file_path, [shape])
                    except ValueError as error:
                        if str(error).startswith('Invalid annotation:'):
                            raise
                        raise ValueError(f'Invalid annotation:\nLabel: {shape.label}\n'
                                         f'Group ID: {shape.group_id}\nReason: {error}') from error
                    f.write(line)
                content = f.getvalue()
                validate_polygon_export(content, image_width, image_height, file_path)
                self._save_annotation_session_before_export(current_tab, canvas)
                write_text_atomic(file_path, content)
            self._mark_annotation_saved(current_tab)

            QMessageBox.information(self, "Success",
                                    "Annotation saved successfully!")

        except Exception as e:
            QMessageBox.critical(self, "Error",
                                 f"Failed to save annotation: {str(e)}")

    def save_rectangle_annotation(self):
        current_shapes = self.get_current_shapes()
        if not current_shapes:
            QMessageBox.warning(self, "Notice", "No shapes to save.")
            return

        # 检查是否有rectangle类型的形状
        has_rectangle = False
        for shape in current_shapes:
            if shape.shape_type == 'rectangle' and shape.visible:
                has_rectangle = True
                break

        if not has_rectangle:
            QMessageBox.warning(self, "Notice", "No visible rectangle annotations to save.")
            return

        # 获取当前文件名作为默认保存文件名的一部分
        current_tab = self.tabWidget.currentWidget()
        default_filename = "Rectangle_Annotation_Exported_by_StomataQuant"
        if current_tab:
            file_path_original = current_tab.property("file_path")
            if file_path_original:
                file_name_without_ext = os.path.splitext(os.path.basename(file_path_original))[0]
                default_filename = f"Rectangle_Annotation_Exported_by_StomataQuant_{file_name_without_ext}.txt"

        # 弹出文件保存对话框，使用默认文件名
        file_path, _ = QFileDialog.getSaveFileName(self,
                                                   "Save YOLO Rectangle Annotation", default_filename,
                                                   "Text Files (*.txt);;All Files (*)")

        if not file_path:
            return

        try:
            canvas = self._require_active_annotation_target(current_tab)
            with io.StringIO() as f:
                for shape in current_shapes:
                    # 只处理rectangle类型
                    if shape.shape_type != 'rectangle' or not shape.visible:
                        continue

                    # 获取图片尺寸用于归一化坐标
                    current_canvas = canvas
                    image_size = current_canvas.image_size
                    image_width = image_size.width()
                    image_height = image_size.height()

                    # 获取矩形的左上角和右下角
                    top_left = shape.pointslist[0]
                    bottom_right = shape.pointslist[1]

                    # 计算中心点及宽高
                    x_center = (top_left.x() + bottom_right.x()) / (2 * image_width)
                    y_center = (top_left.y() + bottom_right.y()) / (2 * image_height)
                    width = abs(bottom_right.x() - top_left.x()) / image_width
                    height = abs(bottom_right.y() - top_left.y()) / image_height

                    # YOLO格式: 类别编号 x中心 y中心 宽度 高度
                    line = f"{shape.classnum} {x_center:.6f} {y_center:.6f} {width:.6f} {height:.6f}\n"
                    f.write(line)
                content = f.getvalue()
                validate_rectangle_export(
                    [shape for shape in current_shapes if shape.shape_type == 'rectangle' and shape.visible],
                    content, 'rectangle', image_width, image_height, file_path)
                self._save_annotation_session_before_export(current_tab, canvas)
                write_text_atomic(file_path, content)
            self._mark_annotation_saved(current_tab)

            QMessageBox.information(self, "Success",
                                    "Annotation saved successfully!")

        except Exception as e:
            QMessageBox.critical(self, "Error",
                                 f"Failed to save annotation: {str(e)}")

    def save_rotated_rectangle_annotation(self):
        current_shapes = self.get_current_shapes()
        if not current_shapes:
            QMessageBox.warning(self, "Notice", "No shapes to save.")
            return

        # 检查是否有rotated_rectangle类型的形状
        has_rotated_rectangle = False
        for shape in current_shapes:
            if shape.shape_type == 'rotated_rectangle' and shape.visible:
                has_rotated_rectangle = True
                break

        if not has_rotated_rectangle:
            QMessageBox.warning(self, "Notice", "No visible rotated rectangle annotations to save.")
            return

        # 获取当前文件名作为默认保存文件名的一部分
        current_tab = self.tabWidget.currentWidget()
        default_filename = "Rotated_Rectangle_Annotation_Exported_by_StomataQuant"
        if current_tab:
            file_path_original = current_tab.property("file_path")
            if file_path_original:
                file_name_without_ext = os.path.splitext(os.path.basename(file_path_original))[0]
                default_filename = f"Rotated_Rectangle_Annotation_Exported_by_StomataQuant_{file_name_without_ext}.txt"

        # 弹出文件保存对话框，使用默认文件名
        file_path, _ = QFileDialog.getSaveFileName(self,
                                                   "Save YOLO OBB Annotation", default_filename,
                                                   "Text Files (*.txt);;All Files (*)")

        if not file_path:
            return

        try:
            canvas = self._require_active_annotation_target(current_tab)
            with io.StringIO() as f:
                for shape in current_shapes:
                    # 只处理rotated_rectangle类型
                    if shape.shape_type != 'rotated_rectangle' or not shape.visible:
                        continue

                    # 获取图片尺寸用于归一化坐标
                    current_canvas = canvas
                    image_size = current_canvas.image_size
                    image_width = image_size.width()
                    image_height = image_size.height()

                    # 检查是否有4个点
                    if len(shape.pointslist) != 4:
                        continue

                    # YOLO OBB格式: 类别编号 x1 y1 x2 y2 x3 y3 x4 y4
                    line = f"{shape.classnum}"

                    # 添加四个角点的归一化坐标
                    for point in shape.pointslist:
                        x = point.x() / image_width
                        y = point.y() / image_height
                        line += f" {x:.17g} {y:.17g}"

                    line += "\n"
                    f.write(line)
                content = f.getvalue()
                validate_rectangle_export(
                    [shape for shape in current_shapes
                     if shape.shape_type == 'rotated_rectangle' and shape.visible],
                    content, 'rotated_rectangle', image_width, image_height, file_path)
                self._save_annotation_session_before_export(current_tab, canvas)
                write_text_atomic(file_path, content)
            self._mark_annotation_saved(current_tab)

            QMessageBox.information(self, "Success",
                                    "Rotated rectangle annotations saved successfully!")

        except Exception as e:
            QMessageBox.critical(self, "Error",
                                 f"Failed to save annotation: {str(e)}")

    ####################################################################
    # ↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑
    # 以上方法多边形/正方形注释的保存或者导入相关
    # Save or Import Polygon/(Rotated) Rectangle Annotation Methods Related to This
    ####################################################################

    ####################################################################
    # 以下方法为去除靠近图像边缘的形状，分别与actionFilterAll/TopLeft/RightBottomEdges按键链接
    # The following methods are for removing shapes near the image edges.
    # They are respectively linked to the buttons "actionFilterAll/TopLeft/RightBottomEdges".
    ####################################################################

    def shape_AllEdges_filter(self):
        view = self.get_current_graphics_view()
        if view is None or view.canvas is None:
            return
        current_canvas = view.canvas
        image_size = current_canvas.image_size
        image_width = image_size.width()
        image_height = image_size.height()
        tolerance = 3  # 设定贴近边界的容差（可以根据需要调整）

        shapes_to_delete = []

        prepared = self._collect_shape_batch(
            current_canvas, 'Filtering shapes...',
            lambda shape: shape if (
                shape.get_bounding_rect().left() <= tolerance or
                shape.get_bounding_rect().right() >= image_width - tolerance or
                shape.get_bounding_rect().top() <= tolerance or
                shape.get_bounding_rect().bottom() >= image_height - tolerance) else None)
        if prepared is None:
            return
        shapes_to_delete = [shape for shape in prepared if shape is not None]

        if shapes_to_delete:
            current_canvas.save_state()  # 保存当前状态以支持撤销
            removed = {id(shape) for shape in shapes_to_delete}
            current_canvas.shapes = [shape for shape in current_canvas.shapes
                                     if id(shape) not in removed]
            current_canvas.update()
            current_canvas.shapesChanged.emit()
            self.update_canvas()
            self.update_shapes_and_label_list()  # 更新列表显示
        print("All edges filter applied.")

    def shape_TopLeft_filter(self):
        view = self.get_current_graphics_view()
        if view is None or view.canvas is None:
            return
        current_canvas = view.canvas
        image_size = current_canvas.image_size
        # image_width = image_size.width()
        # image_height = image_size.height()
        tolerance = 3  # 设定贴近边界的容差

        shapes_to_delete = []

        prepared = self._collect_shape_batch(
            current_canvas, 'Filtering shapes...',
            lambda shape: shape if (
                shape.get_bounding_rect().left() <= tolerance or
                shape.get_bounding_rect().top() <= tolerance) else None)
        if prepared is None:
            return
        shapes_to_delete = [shape for shape in prepared if shape is not None]

        if shapes_to_delete:
            current_canvas.save_state()
            removed = {id(shape) for shape in shapes_to_delete}
            current_canvas.shapes = [shape for shape in current_canvas.shapes
                                     if id(shape) not in removed]
            current_canvas.update()
            current_canvas.shapesChanged.emit()
            self.update_canvas()
            self.update_shapes_and_label_list()  # 更新列表显示
        print("TopLeft filter applied.")

    def shape_RightBottom_filter(self):
        view = self.get_current_graphics_view()
        if view is None or view.canvas is None:
            return
        current_canvas = view.canvas
        image_size = current_canvas.image_size
        image_width = image_size.width()
        image_height = image_size.height()
        tolerance = 3  # 设定贴近边界的容差

        shapes_to_delete = []

        prepared = self._collect_shape_batch(
            current_canvas, 'Filtering shapes...',
            lambda shape: shape if (
                shape.get_bounding_rect().right() >= image_width - tolerance or
                shape.get_bounding_rect().bottom() >= image_height - tolerance) else None)
        if prepared is None:
            return
        shapes_to_delete = [shape for shape in prepared if shape is not None]

        if shapes_to_delete:
            current_canvas.save_state()
            removed = {id(shape) for shape in shapes_to_delete}
            current_canvas.shapes = [shape for shape in current_canvas.shapes
                                     if id(shape) not in removed]
            current_canvas.update()
            current_canvas.shapesChanged.emit()
            self.update_canvas()
            self.update_shapes_and_label_list()  # 更新列表显示
        print("RightBottom filter applied.")

    ####################################################################
    # 以下方法删除Canvas中的形状可以，删除选中的形状或Canvas上的所有形状
    # The following methods can be used to delete shapes in the Canvas.
    # You can either delete the selected shape or all shapes on the Canvas.
    ####################################################################

    def delete_selected_shape(self):
        view = self.get_current_graphics_view()
        if not view or not view.canvas:
            return
        canvas = view.canvas
        selected = {id(s) for s in canvas.selected_shape}
        targets = [s for s in canvas.shapes if id(s) in selected]
        if not targets:
            return
        canvas.save_state()
        blocker = QtCore.QSignalBlocker(canvas)
        try:
            for shape in targets:
                canvas.remove_shape(shape)
            canvas.selected_shape = []
        finally:
            del blocker
        canvas.shapeSelected.emit([])
        canvas.shapesChanged.emit()

    def delete_all_shapes(self):
        """安全地删除所有形状"""
        try:
            # 获取当前图像视图
            current_graphics_view = self.get_current_graphics_view()
            if not current_graphics_view:
                QMessageBox.warning(self, "Notice", "No image is open. Please open an image first.")
                return
                
            # 检查画布是否存在
            canvas = current_graphics_view.canvas
            if not canvas:
                QMessageBox.warning(self, "Notice", "Canvas not available.")
                return
                
            # 检查是否有形状可以删除
            if not canvas.shapes:
                QMessageBox.warning(self, "Notice", "No shapes to delete.")
                return
                
            # 弹出确认对话框
            reply = QMessageBox.question(self, 'Confirm Deletion', 'Do you want to delete all visible shapes?',
                                        QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            if reply == QMessageBox.Yes:
                if not any(shape.visible for shape in canvas.shapes):
                    return
                # 保存当前状态以支持撤销
                canvas.save_state()

                # 暂时禁止画布发送信号和更新
                was_blocked = canvas.blockSignals(True)

                # 创建可见形状的副本以避免迭代时修改列表
                visible_shapes = [shape for shape in canvas.shapes if shape.visible]

                # 使用canvas的remove_shape方法正确删除每个形状
                try:
                    for shape in visible_shapes:
                        canvas.remove_shape(shape)
                    canvas.selected_shape = []
                finally:
                    canvas.blockSignals(was_blocked)
                canvas.update()
                canvas.shapeSelected.emit([])
                canvas.shapesChanged.emit()
                
        except Exception as e:
            QMessageBox.warning(self, "Error", f"An error occurred: {str(e)}")

#############################################################################################################
# 以下代码为程序启动动画
# The following code serves as the entry point for the program to run.
#############################################################################################################

class SplashScreen(QSplashScreen):
    def __init__(self, pixmap):
        super().__init__(pixmap)
        
        # 创建一个进度条
        self.progress_bar = QProgressBar(self)
        self.progress_bar.setMaximum(100)
        progress_bar_height = 20
        bottom_margin = 50  # 增加此值可以使进度条距离底部更远
        self.progress_bar.setGeometry(
            50, 
            pixmap.height() - bottom_margin, 
            pixmap.width() - 100, 
            progress_bar_height
        )
        self.setWindowFlags(Qt.WindowStaysOnTopHint | Qt.FramelessWindowHint)  # 设置窗口标志，无边框且置顶
        
        # 设置进度条样式表
        self.progress_bar.setStyleSheet("""
            QProgressBar {
                border: 2px solid grey;
                border-radius: 5px;
                background-color: rgba(128, 128, 128, 100);
                color: white;
                font-weight: bold;
                text-align: right;
            }
            QProgressBar::chunk {
                background-color: #4CAF50;
                width: 10px;
                margin: 0.3px;
            }
        """)
        
        # 设置字体 - 修改为加粗字体
        if sys.platform == "darwin":
            self.font = QFont()
            self.font.setBold(True)
        else:
            self.font = QFont("微软雅黑", 10, QFont.Bold)  # 添加 QFont.Bold 使字体加粗
        self.setFont(self.font)
        
        # 保存当前消息
        self.current_message = ""
        self.message_alignment = Qt.AlignBottom | Qt.AlignHCenter

    def drawContents(self, painter):
        """重写绘制内容方法以添加半透明背景"""
        # 调用父类的绘制方法
        # super().drawContents(painter)
        
        if self.current_message:
            # 设置字体
            painter.setFont(self.font)
            
            # 计算文本区域
            fm = painter.fontMetrics()
            text_rect = fm.boundingRect(self.rect(), self.message_alignment, self.current_message)
            
            # 扩展文本区域以添加一些内边距
            padding = 10
            bg_rect = text_rect.adjusted(-padding, -padding, padding, padding)
            
            # 绘制半透明背景
            painter.fillRect(bg_rect, QColor(128, 128, 128, 100))
            
            # 设置画笔颜色为纯白色
            painter.setPen(QColor(255, 255, 255))
            
            # 绘制文本
            painter.drawText(self.rect(), self.message_alignment, self.current_message)
            

    def showMessage(self, message, alignment=Qt.AlignBottom | Qt.AlignHCenter, color=Qt.white):
        """重写showMessage以保存当前消息和对齐方式"""
        self.current_message = message
        self.message_alignment = alignment
        # 调用父类的showMessage方法，确保使用纯白色
        super().showMessage(message, alignment, Qt.white)

    def set_progress(self, value):
        """更新进度条"""
        self.progress_bar.setValue(value)
        msg = f"StomataQuant: Quantify Plant Epidermis Instantly... {value}%"
        self.showMessage(msg, Qt.AlignBottom | Qt.AlignHCenter, Qt.white)
        QApplication.processEvents()

#############################################################################################################
# 以下代码为程序运行入口
# The following code serves as the entry point for the program to run.
#############################################################################################################

if __name__ == "__main__":
    import multiprocessing
    import traceback
    import sys
    import faulthandler
    from PyQt5.QtWidgets import QMessageBox

    faulthandler.enable()  # 启用故障处理器以获取更好的崩溃信息


    # 定义增强的全局异常钩子
    def exception_hook(exctype, value, tb):
        """显示未捕获异常的对话框并打印堆栈跟踪"""
        error_msg = ''.join(traceback.format_exception(exctype, value, tb))
        print(f"Uncaught exception:\n{error_msg}")

        # 使用对话框显示错误信息
        if QApplication.instance():
            QMessageBox.critical(
                None,
                "程序错误|Programming error",
                f"程序遇到了一个未处理的错误:\n\n{str(value)}\n\n详细信息已打印到控制台。\n\nThe program encountered an unhandled error:\n\n{str(value)}\n\nThe detailed information has been printed to the console.",
                QMessageBox.Ok
            )
        sys.exit(1)
    # 安装全局异常钩子
    sys.excepthook = exception_hook
    
    multiprocessing.freeze_support()
    app = QApplication(sys.argv)
    app_icon = QtGui.QIcon(":/ICON.png")
    if sys.platform == 'darwin' and app_icon.isNull():
        bundled_icon = macos_resource_path('ICON.png')
        if bundled_icon:
            app_icon = QtGui.QIcon(bundled_icon)
    app.setWindowIcon(app_icon)
    if sys.platform == "win32":
        font = QFont("微软雅黑", 10)
        app.setFont(font)

    try:
        # 创建启动画面
        splash_pix = QPixmap(":/Start_up.png")  # 替换为你的启动画面图片路径
        if sys.platform == 'darwin' and splash_pix.isNull():
            bundled_splash = macos_resource_path('Start_up.png')
            if bundled_splash:
                splash_pix = QPixmap(bundled_splash)
        splash = SplashScreen(splash_pix)
        splash.show()
        
        # 模拟加载过程 - 在实际应用中结合实际初始化任务
        splash.set_progress(10)
        splash.showMessage("Loading the program core...", Qt.AlignBottom | Qt.AlignHCenter, Qt.white)
        app.processEvents()
        time.sleep(0.35)  # 模拟程序核心加载时间
        
        splash.set_progress(40)
        splash.showMessage("Initializing UI components...", Qt.AlignBottom | Qt.AlignHCenter, Qt.white)
        app.processEvents()
        time.sleep(0.35)  # 模拟UI组件初始化时间
        
        splash.set_progress(70)
        splash.showMessage("Configuring the system environment...", Qt.AlignBottom | Qt.AlignHCenter, Qt.white)
        app.processEvents()
        time.sleep(0.35)  # 模拟系统环境配置时间
        
        # 创建主窗口实例
        GUI_Main = UIMainWindow()
        
        splash.set_progress(90)
        splash.showMessage("Ready for StomataQuant...", Qt.AlignBottom | Qt.AlignHCenter, Qt.white)
        app.processEvents()
        time.sleep(0.5)# 短暂延迟
        
        splash.set_progress(100)
        app.processEvents()
        
        # 隐藏启动画面，显示主窗口
        splash.finish(GUI_Main)

        GUI_Main.show()
        sys.exit(app.exec_())

    except Exception as e:
        # 处理启动过程中的异常
        error_detail = traceback.format_exc()
        print(f"程序启动出错(The program failed to start properly):\n{error_detail}")
        QMessageBox.critical(
            None,
            "启动错误(Start-up error)",
            f"程序启动时出现错误(An error occurred when the program started up.):\n\n{str(e)}",
            QMessageBox.Ok
        )
        sys.exit(1)
