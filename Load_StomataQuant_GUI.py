import sys
import os
from PyQt5.QtCore import Qt, QTimer, QEventLoop,QPluginLoader, QCoreApplication, QtMsgType, qInstallMessageHandler
from PyQt5.QtGui import QImageReader
import PyQt5
# 设置插件路径 Set the plug-in path
if 'QT_PLUGIN_PATH' in os.environ:
    print(os.environ['QT_PLUGIN_PATH'])
    del os.environ['QT_PLUGIN_PATH']

os.environ["QT_QPA_PLATFORM_PLUGIN_PATH"] = os.path.join(os.path.dirname(sys.executable), "Library", "plugins", "platforms")
plugin_path = os.path.join(os.path.dirname(PyQt5.__file__), 'Qt', 'plugins')
os.environ['QT_PLUGIN_PATH'] = plugin_path
print('==============================', os.environ['QT_PLUGIN_PATH'])

# 添加库路径 Add library path
QCoreApplication.addLibraryPath(plugin_path)
print("The loaded library path：", QCoreApplication.libraryPaths())

# 检查支持的图像格式 Check supported image formats
formats = QImageReader.supportedImageFormats()
print(formats)

# 导入核心包 Import core packages
import gc
import tempfile
import json
import time
from collections import defaultdict
from PyQt5 import QtCore, QtGui, QtWidgets
from PyQt5.QtCore import QPointF, QRect, QRectF, Qt, pyqtSignal, QThread,QFile, QIODevice
from PyQt5.QtGui import (QFont, QImage, QKeySequence, QPixmap, QTransform)
from PyQt5.QtWidgets import (QApplication, QDialog, QFileDialog, QLabel, QLineEdit, QMessageBox,
                             QProgressBar, QShortcut, QSplashScreen, QVBoxLayout, QWidget,QProgressDialog)


# 导入自定义模块 Import custom modules
from StomataQuant_GUI import MainWindow
from ultralytics import YOLO
from AllDialogs import InferenceSettingsDialog,SetMeasuringScaleDialog,LabelInputDialog,ProgressDialog,ColorSettingsDialog,HeatMapDialog,BatchProcessingDialog,BatchProgressDialog
from ImageGraphicsView import ImageGraphicsView
from shape import *
from canvas import Canvas, USE_NUMBA, check_numba,process_polygon_data
from dock_widgets import ShapeListDock, LabelListDock,MeasuredResultsDock,ImageResultsSummaryDock
from InferenceThread import YOLOSegInferenceThread,PolygonProcessThread,ABorADInferenceThread, HeatMapGenerationThread
from BatchProcessor import BatchProcessor, BatchExporter, BatchImporter
import resources_rc
#############################################################################################################
# UIMainWindow
# 主窗口类，继承自MainWindow
#############################################################################################################

class UIMainWindow(MainWindow):
    def __init__(self):
        super().__init__()
        if not check_numba():
            USE_NUMBA = False
            print("Numba is unavailable and acceleration has been disabled.")
        self.setupUi(self)
        self._noShapeListSelectionSlot = False
        self._noCanvasSelectionSlot = False
        # 添加全局状态变量控制 group_id 是否显示
        self._global_show_group_id = False

        # 初始化 MeasuredResultsDock

        self.image_results_summary_dock = ImageResultsSummaryDock(self)
        self.addDockWidget(Qt.RightDockWidgetArea, self.image_results_summary_dock)
        self.measured_results_dock = MeasuredResultsDock(self)
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
        self.actionColorSettings.triggered.connect(self.show_color_settings)
        self.actionOpen.triggered.connect(self.open_file)
        self.opened_files = []  # 以跟踪打开的文件，防止重复添加文件
        ## 链接到保存按钮
        self.actionSavePolygonAnnotataion.triggered.connect(self.save_polygon_annotation)
        self.actionImportPolygonAnnotataion.triggered.connect(self.import_polygon)
        self.actionSaveRectangleAnnotataion.triggered.connect(self.save_rectangle_annotation)
        self.actionImportRectangleAnnotataion.triggered.connect(self.import_rectangle)
        self.actionSaveRotatedRectangleAnnotataion.triggered.connect(self.save_rotated_rectangle_annotation)
        self.actionImportRotatedRectangleAnnotataion.triggered.connect(self.import_rotated_rectangle)
        self.actionShowPoint.triggered.connect(self.show_points)
        self.actionShowID.triggered.connect(self.draw_group_id)

        # 链接到模型选择
        self.actionModelSetting.triggered.connect(self.load_model)  
        self.model = None  # Initialize the model attribute
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
        self.tabWidget.tabCloseRequested.connect(self.close_tab)

        # # 链接shapedockinstance中选中某个列信号到on_shape_selected_in_dock
        self.shapedockinstance.selectionClickedinShapeList.connect(self.on_shape_selected_in_dock)
        
        # 链接shapedockinstance中可视性更改信号到update_canvas
        self.shapedockinstance.visibilityChanged.connect(self.update_canvas)
        # 链接labeldockinstance中可视性更改信号到on_label_visibility_changed
        self.labeldockinstance.visibilityChanged.connect(self.on_label_visibility_changed)
        # 连接动作
        self.actionGetMER.triggered.connect(self.Get_MER_on_Canvas)
        self.actionFeatureExtraction.triggered.connect(self.feature_extraction_of_all_shapes)
        self.actionDuplicate.triggered.connect(self.duplicate_shape)

        self.backspace_shortcut = QShortcut(QKeySequence("Backspace"), self)
        self.backspace_shortcut.activated.connect(self.delete_selected_shape)
        self.delete_shortcut = QShortcut(QKeySequence("Delete"), self)
        self.delete_shortcut.activated.connect(self.delete_selected_shape)
        self.copy_shortcut = QShortcut(QKeySequence("Ctrl+C"), self)
        self.copy_shortcut.activated.connect(self.duplicate_shape)
        self.revoke_shortcut = QShortcut(QKeySequence("Ctrl+Z"), self)
        self.revoke_shortcut.activated.connect(self.undo)
        self.space_shortcut = QShortcut(QKeySequence("Ctrl+Space"), self)
        self.space_shortcut.activated.connect(self.fit_to_view)
        
        
        self.featureextract_shortcut = QShortcut(QKeySequence("Ctrl+F"), self)
        self.featureextract_shortcut.activated.connect(self.feature_extraction_of_all_shapes)
        # self.getmer_shortcut = QShortcut(QKeySequence("Ctrl+G"), self)
        # self.getmer_shortcut.activated.connect(self.Get_MER_on_Canvas)
        self.ai_shortcut = QShortcut(QKeySequence("Ctrl+I"), self)
        self.ai_shortcut.activated.connect(self.run_YOLO_seg_inference)
        
        # 添加这些新快捷键
        self.ctrl_shift_delete_shortcut = QShortcut(QKeySequence("Ctrl+Shift+Delete"), self)
        self.ctrl_shift_delete_shortcut.activated.connect(self.delete_all_shapes)
        self.ctrl_shift_backspace_shortcut = QShortcut(QKeySequence("Ctrl+Shift+Backspace"), self)
        self.ctrl_shift_backspace_shortcut.activated.connect(self.delete_all_shapes)

        # 添加批处理快捷键
        self.batch_processing_shortcut = QShortcut(QKeySequence("Ctrl+B"), self)
        self.batch_processing_shortcut.activated.connect(self.batch_processing)

        
        self.selectmodel_shortcut = QShortcut(QKeySequence("Ctrl+M"), self)
        self.selectmodel_shortcut.activated.connect(self.load_model)

        self.openfile_shortcut = QShortcut(QKeySequence("Ctrl+O"), self)
        self.openfile_shortcut.activated.connect(self.open_file)
        
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

                # 在__init__方法的末尾添加
        self.actionShortcutHelp.triggered.connect(self.show_shortcut_help)
        self.actionSeeHelp.triggered.connect(self.show_help)

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
        """显示所有可用的键盘快捷键，使用非模态窗口"""
        # 如果已经存在快捷键窗口，则显示它
        if hasattr(self, 'shortcut_dialog') and self.shortcut_dialog.isVisible():
            self.shortcut_dialog.raise_()
            self.shortcut_dialog.activateWindow()
            return
        
        # 创建一个非模态对话框
        self.shortcut_dialog = QtWidgets.QDialog(self)
        self.shortcut_dialog.setWindowTitle("Keyboard Shortcuts")
        self.shortcut_dialog.setWindowFlags(
            QtCore.Qt.Window | 
            QtCore.Qt.WindowStaysOnTopHint | 
            QtCore.Qt.WindowCloseButtonHint
        )
        
        # 设置大小和位置
        self.shortcut_dialog.resize(500, 600)
        # 居中显示在主窗口上
        center_point = self.geometry().center()
        dialog_rect = self.shortcut_dialog.geometry()
        dialog_rect.moveCenter(center_point)
        self.shortcut_dialog.setGeometry(dialog_rect)
        
        # 创建布局
        layout = QtWidgets.QVBoxLayout(self.shortcut_dialog)
        
        # 设置快捷键文本
        shortcut_text = """
    <h3>Keyboard Shortcuts</h3>
    <table border="0" cellspacing="10">
        <tr><th colspan="2" align="left">File Operations</th></tr>
        <tr>
            <td><b>Ctrl+O</b></td>
            <td>Open File</td>
        </tr>
        
        <tr><th colspan="2" align="left">Analysis & Processing</th></tr>
        <tr>
            <td><b>Ctrl+F</b></td>
            <td>Feature Extraction</td>
        </tr>
        <tr>
            <td><b>Ctrl+I</b></td>
            <td>Run AI Inference</td>
        </tr>
        <tr>
            <td><b>Ctrl+M</b></td>
            <td>Select Model</td>
        </tr>
        <tr>
            <td><b>Ctrl+B</b></td>
            <td>Batch Processing</td>
        </tr>

        <tr><th colspan="2" align="left">Shape Operations</th></tr>
        <tr>
            <td><b>Ctrl+Z</b></td>
            <td>Undo Operation</td>
        </tr>
        <tr>
            <td><b>Ctrl+C</b></td>
            <td>Copy/Clone Selected Shape</td>
        </tr>
        <tr>
            <td><b>Delete</b> / <b>Backspace</b></td>
            <td>Delete Selected Shape</td>
        </tr>
        <tr>
            <td><b>Ctrl+Shift+Delete</b> / <b>Ctrl+Shift+Backspace</b></td>
            <td>Delete All Shapes</td>
        </tr>
        
        <tr><th colspan="2" align="left">View Controls</th></tr>
        <tr>
            <td><b>Ctrl+Space</b></td>
            <td>Fit to View</td>
        </tr>
        <tr>
            <td><b>Ctrl+Mouse Wheel</b></td>
            <td>Zoom In/Out</td>
        </tr>
        <tr>
            <td><b>Ctrl++</b> / <b>Ctrl+-</b></td>
            <td>Zoom In/Out</td>
        </tr>
    </table>
    """
        # 使用QTextBrowser以支持富文本和滚动条
        text_browser = QtWidgets.QTextBrowser()
        text_browser.setHtml(shortcut_text)
        text_browser.setOpenExternalLinks(True)
        layout.addWidget(text_browser)
        
        # 添加关闭按钮（可选）
        close_button = QtWidgets.QPushButton("Close")
        close_button.clicked.connect(self.shortcut_dialog.close)
        layout.addWidget(close_button)
        
        # 显示对话框(非模态)
        self.shortcut_dialog.show()
    #批量导入
    # 修改批量导入方法如下:
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
        # 检查是否已加载模型（如果需要运行AI功能）
        if hasattr(self, 'model') and self.model:
            try:
                processor = BatchProcessor(self)
                processor.process()
            except Exception as e:
                QMessageBox.warning(self, "Error", f"Error during batch processing: {e}")
        else:
            QMessageBox.warning(self, "Notice", "Please load a model first.")
            return
        


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
            QApplication.instance().quit()

    ### 启动Edit模式，控制其他按钮开启还是关闭
    ### Start the Edit mode and control whether other buttons are enabled or disabled.
    def edit_shapes(self):
        try:
            currentshapes = self.get_current_shapes()
            has_shapes = bool(self.get_current_shapes())
            self.actionDeleteAllShapes.setEnabled(has_shapes)
            self.actionFeatureExtraction.setEnabled(has_shapes)
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
        dialog = SetMeasuringScaleDialog(self)
        if dialog.exec_():
            pixel_distance, real_distance, unit, is_global = dialog.get_scale_info()

            if pixel_distance == 0:
                QMessageBox.warning(self, "Notice", "The pixel distance cannot be zero.")
                return
            
            scale = real_distance / pixel_distance  # 每像素对应的实际长度
            scale_info = {'scale': scale, 'unit': unit}
            if is_global:
                self.global_scale_info = scale_info
            else:
                current_view = self.get_current_graphics_view()
                if current_view:
                    current_view.scale_info = scale_info

    ###“Feature Extraction”按键所连接的功能： 关于各种形状的特征提取，主要依赖于shape中定义的方法
    ### The function connected by the "Feature Extraction" button:
    # Regarding the feature extraction of various shapes, it mainly relies on the methods defined in the "shape" section.
    def feature_extraction_of_all_shapes(self):
        get_current_shapes = self.get_current_shapes()
        visible_shapes = [s for s in get_current_shapes if s.visible]
                # 获取比例尺信息
        current_view = self.get_current_graphics_view()
        canvas = current_view.canvas
        image_size = canvas.image_size
        image_width = image_size.width()
        image_height = image_size.height()

        if hasattr(self, 'global_scale_info'):
            scale_info = self.global_scale_info
        else:
            current_view = self.get_current_graphics_view()
            if current_view and hasattr(current_view, 'scale_info'):
                scale_info = current_view.scale_info
            else:
                scale_info = None  # 如果没有设置比例尺，则为 None
    

        for s in visible_shapes:
            if s.shape_type == "polygon":
                s.feature_extraction_polygon(scale_info=scale_info)
            if s.shape_type == "rectangle":
                s.feature_extraction_rectangle(scale_info=scale_info)
            if s.shape_type == "rotated_rectangle":
                s.feature_extraction_rotated_rectangle(scale_info=scale_info)
            if s.shape_type == "line":
                s.feature_extraction_line(scale_info=scale_info)
            if s.shape_type == "point":
                s.feature_extraction_point(scale_info=scale_info)


        # # 清空当前的 QTableWidget
        # self.measured_results_dock.populate([])
        # # 提供默认的 image_width 和 image_height
        # self.image_results_summary_dock.populate([], 0, 0, None)
        # 填充 QTableWidget
        self.measured_results_dock.populate(visible_shapes)
        self.image_results_summary_dock.populate(visible_shapes, image_width, image_height, scale_info)

    ### GETMER按钮-可以获得多边形的最小外接矩形MER，
    ### 主要使用了shape中定义的calculate_minimum_rotated_rectangle方法
    ### GETMER Button - It can obtain the minimum enclosing rectangle of a polygon MER.
    ### It mainly utilizes the calculate_minimum_rotated_rectangle method defined in the shape module.
    def Get_MER_on_Canvas(self):
        # 目前仅有长宽的测定
        canvas = self.get_current_graphics_view().canvas
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
            

        new_shapes = []
        for shape in canvas.shapes:
            if shape.visible and shape.shape_type == "polygon":
            # 调用修改后的方法，获取新形状
                rotated_rect_shape = shape.calculate_minimum_rotated_rectangle()
                if rotated_rect_shape:
                    new_shapes.append(rotated_rect_shape)
        # 将新形状添加到 canvas.shapes 中
        canvas.shapes.extend(new_shapes)
        # 更新形状列表和画布
            # 临时保存并清除选中状态
        temp_selected = canvas.selected_shape.copy() if canvas.selected_shape else []
        canvas.selected_shape = []
        self.update_shapes_and_label_list()
        self.update_canvas()
        canvas.selected_shape = temp_selected
        self.actionGetMER.setEnabled(False)


    ### 功能实现--绘制形状的ID
    ### Function - Show ID for Drawing Shapes
    def draw_group_id(self):
        current_shapes = self.get_current_shapes()
        if not current_shapes:
            QMessageBox.warning(self, "Notice", "No shapes to show.")
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

        # 标记转换前保存状态
        current_canvas.save_state()

        # 转换可见的形状为点，并正确标记脏状态
        shapes_changed = False
        for shape in current_shapes:
            if shape.visible:
                # 记录原始类型
                original_type = shape.shape_type
                if original_type not in ["point"]:  # 避免重复转换点形状
                    shape.convert_to_point_shape()
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
            if not canvas.undo_stack:
                QMessageBox.warning(self, "Notice", "There is no reversible operation.")
                return
                
            # 执行撤销操作
            canvas.undo()
            self.update_shapes_and_label_list()
        except Exception as e:
            QMessageBox.warning(self, "Error", f"An error occurred during the cancellation operation: {str(e)}")
    def update_undo_button(self):
        """更新撤销按钮的状态，增加对空画布的检查"""
        current_graphics_view = self.get_current_graphics_view()
        
        # 检查是否有有效的图形视图
        if current_graphics_view is None:
            # 没有打开标签页，禁用撤销按钮
            self.actionUndo.setEnabled(False)
            return
        
        # 检查是否有有效的画布
        canvas = current_graphics_view.canvas
        if canvas is None:
            self.actionUndo.setEnabled(False)
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
        canvas = self.get_current_graphics_view().canvas
        if not canvas.selected_shape:
            return

        # 获取当前最大的group_id
        existing_shapes = self.get_current_shapes()
        max_group_id = max([s.group_id for s in existing_shapes if s.group_id is not None], default=-1)

        # 复制每个选中的形状
        for shape in canvas.selected_shape:
            new_shape = shape.copy()  # 使用Shape类的自定义copy方法
            # 递增group_id
            max_group_id += 1
            new_shape.group_id = max_group_id
            # 稍微偏移位置以区分
            new_shape.moveBy(10, 10)
            # 添加到画布
            canvas.add_shape(new_shape)  # 使用add_shape方法
            new_shape.update_shape()

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
        for shape in self.get_current_shapes():
            if shape.label == label:
                shape.visible = visible
        self.shapedockinstance.update_visibility()
        self.get_current_graphics_view().update()

    # 当在窗口列选择，在Canvas中显示
    # When selecting in the window column, it will be displayed in the Canvas.
    def on_shape_selected_in_dock(self, selected_rows_in_dock):
        """安全处理在 dock 中选择形状的事件"""
        self._noShapeListSelectionSlot = True

        try:
            # 如果另一个事件处理已经激活，则直接返回
            if self._noCanvasSelectionSlot:
                return
                
            # 获取当前图像视图
            current_graphics_view = self.get_current_graphics_view()
            if not current_graphics_view:
                print("Warning: No current graphics view available.")
                return
                
            # 检查画布是否存在
            canvas = current_graphics_view.canvas
            if not canvas:
                print("Warning: No canvas available in current graphics view.")
                return
                
            # 清除所有形状的选中状态
            for shape in canvas.shapes:
                shape.selected = False
                
            # 更新选中状态
            for shape in selected_rows_in_dock:
                shape.selected = True
                
            canvas.selected_shape = selected_rows_in_dock.copy()
            canvas.update()

            # 更新工具栏按钮状态
            has_selected = bool(canvas.selected_shape)
            self.actionDuplicate.setEnabled(has_selected)
            self.actionDelete.setEnabled(has_selected)

        except Exception as e:
            print(f"Error in on_shape_selected_in_dock: {e}")
        finally:
            self._noShapeListSelectionSlot = False

    # 当 canvas 中的某个形状被选中时，触发 shapeSelected 信号，并调用这个槽函数。
    # When a certain shape in the canvas is selected
    def on_shape_selected_in_canvas(self, canvas_selected_shapes):
        """安全处理在 canvas 中选择形状的事件"""
        self._noCanvasSelectionSlot = True
        try:
            # 如果另一个事件处理已经激活，则直接返回
            if self._noShapeListSelectionSlot:
                return
                
            # 获取当前图像视图
            current_graphics_view = self.get_current_graphics_view()
            if not current_graphics_view:
                print("Warning: No current graphics view available.")
                return
                
            # 检查画布是否存在
            canvas = current_graphics_view.canvas
            if not canvas:
                print("Warning: No canvas available in current graphics view.")
                return
                
            # 清除之前选择的形状
            for s in canvas.selected_shape:
                s.selected = False
                
            self.shapedockinstance.clearSelection()
            canvas.selected_shape = canvas_selected_shapes

            if len(canvas_selected_shapes) == 1:
                s = canvas_selected_shapes[0]
                s.selected = True
                row = self.shapedockinstance.findItemByShape(s)
                if row >= 0:  # 检查是否找到了有效的行
                    self.shapedockinstance.selectItem(row)
                    self.shapedockinstance.scrollToItem(row)
            else:
                rows_to_select = []
                for s in canvas_selected_shapes:
                    s.selected = True
                    row = self.shapedockinstance.findItemByShape(s)
                    rows_to_select.append(row)
                self.shapedockinstance.selectItems(rows_to_select)
                if rows_to_select:
                    self.shapedockinstance.scrollToItem(rows_to_select[-1])
                    
            # 更新工具栏按钮状态
            has_selected = bool(canvas.selected_shape)
            self.actionDuplicate.setEnabled(has_selected)
            self.actionDelete.setEnabled(has_selected)
            
        except Exception as e:
            print(f"Error in on_shape_selected_in_canvas: {e}")
        finally:
            self._noCanvasSelectionSlot = False

    # 更新dock窗口中的操作状 Update the operation status in the dock window

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

            # 发送shapes changed信号
            current_canvas.shapesChanged.emit()
            
        except Exception as e:
            print(f"Error in update_actions_inDocks: {e}")

    # 如果标签页改变，更新缩放标签，更新形状列表和标签列表
    def on_tab_changed_and_update_zoom_and_list(self, index):
        """标签页变化时的处理，确保安全处理特殊情况"""
        # 检查索引是否有效（有可能是 -1，表示没有标签页）
        if index < 0 or index >= self.tabWidget.count():
            # 没有标签页，禁用相关操作
            self.actionUndo.setEnabled(False)
            return
            
        # 原有的更新缩放和列表
        self.update_zoom_on_tab_change(index)
        self.update_list_on_tab_changed(index)
        
        # 更新 undo 按钮状态
        self.update_undo_button()

        # 更新shapedockinstance与labeldockinstance窗口
    def update_list_on_tab_changed(self, index):
        current_graphics_view = self.get_current_graphics_view()
        if current_graphics_view is not None:
            current_canvas = current_graphics_view.canvas

            image_size = current_canvas.image_size
            image_width = image_size.width()
            image_height = image_size.height()

            if hasattr(self, 'global_scale_info'):
                scale_info = self.global_scale_info
            else:
                if hasattr(current_graphics_view, 'scale_info'):
                    scale_info = current_graphics_view.scale_info
                else:
                    scale_info = None  # 如果没有设置比例尺，则为 None

            if current_canvas.shapes:
                shapes = getattr(current_canvas, 'shapes', [])
                for s in shapes:
                    s.selected = False

                self.shapedockinstance.populate(shapes)
                self.labeldockinstance.populate(shapes, Shape.get_color_by_classnum)
                visible_shapes = [s for s in shapes if s.visible]

                self.actionEditShapes.setChecked(True)
                self.actionFilterAllEdges.setEnabled(True)
                self.actionFilterTopLeft.setEnabled(True)
                self.actionFilterRightBottom.setEnabled(True)
                self.actionFeatureExtraction.setEnabled(True)
                self.actionDeleteAllShapes.setEnabled(True)

                if any(s.shape_type == "polygon" for s in shapes):
                    self.actionGetMER.setEnabled(True)
                else:
                    self.actionGetMER.setEnabled(False)

                if any(s.feature_results for s in visible_shapes):
                    self.measured_results_dock.populate(visible_shapes)
                    self.image_results_summary_dock.populate(visible_shapes, image_width, image_height, scale_info)
                else:
                    self.measured_results_dock.populate([])
                    # 提供默认的 image_width 和 image_height
                    self.image_results_summary_dock.populate([], 0, 0, None)
            else:
                self.shapedockinstance.populate([])
                self.labeldockinstance.populate([], Shape.get_color_by_classnum)
                self.measured_results_dock.populate([])
                # 提供默认的 image_width 和 image_height
                self.image_results_summary_dock.populate([], 0, 0, None)

                self.actionEditShapes.setChecked(False)
                self.actionFilterAllEdges.setEnabled(False)
                self.actionFilterTopLeft.setEnabled(False)
                self.actionFilterRightBottom.setEnabled(False)
                self.actionFeatureExtraction.setEnabled(False)
                self.actionDeleteAllShapes.setEnabled(False)
                self.actionGetMER.setEnabled(False)
        else:
            # 当没有打开的标签页时，清空所有列表，并提供默认的图像尺寸和比例尺信息
            self.shapedockinstance.populate([])
            self.labeldockinstance.populate([], Shape.get_color_by_classnum)
            self.measured_results_dock.populate([])
            # 这里提供默认的 image_width 和 image_height
            self.image_results_summary_dock.populate([], 0, 0, None)
            self.actionFilterAllEdges.setEnabled(False)
            self.actionFilterTopLeft.setEnabled(False)
            self.actionFilterRightBottom.setEnabled(False)
            self.actionFeatureExtraction.setEnabled(False)
            self.actionDeleteAllShapes.setEnabled(False)
            self.actionGetMER.setEnabled(False)

    ### 更新当前canvas Update the current canvas
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
            
        except Exception as e:
            print(f"Error in update_canvas: {e}")

    def on_shapes_changed_in_canvas(self):
        self.update_shapes_and_label_list()
        self.update_undo_button()
        # self.update_filter_actions()

    def update_shapes_and_label_list(self):
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
            has_selected = bool(canvas.selected_shape)
            
            # 更新形状列表显示
            if has_selected:
                pass
            else:
                self.shapedockinstance.populate(shapes)
                self.labeldockinstance.populate(shapes, Shape.get_color_by_classnum)
                
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
        """处理 zoomChanged 信号，更新 QLineEdit。"""
        self.zoomLineEdit.blockSignals(True)
        self.zoomLineEdit.setText(f"{value}%")
        self.zoomLineEdit.blockSignals(False)
        # 更新 zoomSlider
        self.zoomSlider.blockSignals(True)
        self.zoomSlider.setValue(value)
        self.zoomSlider.blockSignals(False)
        # 更新 Canvas 的 scale_factor
        current_graphics_view = self.get_current_graphics_view()
        if current_graphics_view and current_graphics_view.canvas:
            scale_factor = value / 100.0
            current_graphics_view.canvas.set_scale_factor(scale_factor)
            current_graphics_view.canvas.update()


    # 对应GUI上鼠标位置标签的改变对于鼠标位置改变时候，更新QLabel
    # Corresponding to the change of the mouse position label on the GUI, update QLabel when the mouse position changes.
    def update_mouse_position(self, x, y):
        try:
            current_graphics_view = self.get_current_graphics_view()
            if current_graphics_view and current_graphics_view.pixmap_item:
                pixmap = current_graphics_view.pixmap_item.pixmap()
                if not pixmap.isNull():
                    image = pixmap.toImage()
                    if 0 <= x < image.width() and 0 <= y < image.height():
                        # 鼠标在图像范围内
                        self.mousePositionLabel.setText(f"Mouse Position: (x={x}, y={y}); ")
                    else:
                        # 鼠标在图像范围外
                        self.mousePositionLabel.setText("Mouse Position: N/A; ")
                else:
                    self.mousePositionLabel.setText("Mouse Position: N/A; ")
            else:
                self.mousePositionLabel.setText("Mouse Position: N/A; ")
        except Exception as e:
            print(f"Error in update_mouse_position: {e}")

    # 对应GUI上像素值标签的改变对于像素值改变时候，更新QLabel
    # When the pixel value changes, update the QLabel corresponding to the change of the pixel value label on the GUI.
    def update_pixel_value(self, r, g, b):
        try:
            if r == -1 and g == -1 and b == -1:
                # 当接收到 -1，表示鼠标在图像范围外，显示 "N/A"
                self.pixelValueLabel.setText("Pixel Value: N/A; ")
            else:
                self.pixelValueLabel.setText(f"Pixel Value: R={r}, G={g}, B={b}; ")
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
            scale_factor = value / 100.0
            current_graphics_view.resetTransform()  # 先重置变换，避免累积缩放
            current_graphics_view.scale(scale_factor, scale_factor)  # 应用新的缩放比例
            current_graphics_view.current_zoom = value
            current_graphics_view.zoomChanged.emit(value)  # 确保发射信号
            # 更新 QLineEdit
            self.handle_zoom_changed(value)  # 直接调用新的处理方法

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
                    self.zoomLineEdit.setText(f"{current_zoom}%")
                    self.zoomLineEdit.blockSignals(False)

                    self.zoomSlider.blockSignals(True)
                    self.zoomSlider.setValue(int(current_zoom))
                    self.zoomSlider.blockSignals(False)

                    self.imageSizeLabel.setText(f"Image Size: {pixmap.width()}x{pixmap.height()} pixels; ")
                    try:
                        file_size = os.path.getsize(file_path)
                        self.fileSizeLabel.setText(f"File Size: {file_size / 1024:.2f} KB; ")
                    except OSError as e:
                        self.fileSizeLabel.setText("File Size: N/A; ")
                        print(f"Error getting file size: {e}")
                else:
                    print("Pixmap is null.")
                    self.imageSizeLabel.setText("Image Size: N/A; ")
                    self.fileSizeLabel.setText("File Size: N/A; ")
            else:
                print("GraphicsView 或 pixmap_item 不存在，或 file_path 是 None。")
                self.imageSizeLabel.setText("Image Size: N/A; ")
                self.fileSizeLabel.setText("File Size: N/A; ")
        else:
            print("The current TAB page does not exist。")
            self.imageSizeLabel.setText("Image Size: N/A; ")
            self.fileSizeLabel.setText("File Size: N/A; ")

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
            existing_shapes = [s for s in self.get_current_shapes() if s != shape]
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

        existing_shapes = [s for s in self.get_current_shapes() if s != shape]
        existing_same_label_shapes = []
        existing_same_type_shapes = []

        for s in existing_shapes:
            if s.label == label:
                existing_same_label_shapes.append(s)
                print(f"existing_same_label_shapes: {existing_same_label_shapes}")
                print(f"existing_same_type_shapes: {bool(existing_same_label_shapes)}")
            if s.label == label and s.shape_type == shape.shape_type:
                existing_same_type_shapes.append(s)
                print(f"existing_same_type_shapes: {existing_same_type_shapes}")
                print(f"existing_same_type_shapes: {bool(existing_same_type_shapes)}")

        if existing_same_label_shapes:
            # 如果标签已存在，使用相同的属性
            shape.classnum = existing_same_label_shapes[0].classnum

            if existing_same_type_shapes:
                max_group_id = max(s.group_id for s in existing_same_type_shapes)
                shape.group_id = max_group_id + 1
            else:
                # 如果不存在相同 shape_type 的形状，group_id 从 0 开始重新编号
                shape.group_id = 0
        else:
            # 如果是新标签，分配新的 classnum 和 group_id
            # 获取当前最大的 classnum
            max_classnum = -1
            for s in existing_shapes:
                if s.classnum is not None and s.classnum > max_classnum:
                    max_classnum = s.classnum
                else:
                    max_classnum = -1
            shape.classnum = max_classnum + 1
            shape.group_id = 0

        # 更新 UI
        self.labeldockinstance.add_label(shape.label)
        self.shapedockinstance.add_shape(shape)
        self.update_actions_inDocks()

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

    def open_file(self):
        options = QFileDialog.Options()
        file_paths, _ = QFileDialog.getOpenFileNames(self, "Select image files", "",
                                                    "Image Files (*.png *.jpg *.jpeg *.bmp *.tif);;All Files (*)",
                                                    options=options)
        for file_path in file_paths:
            if file_path and file_path not in self.opened_files:
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
                
                # 将文件添加到已打开文件列表中
                self.opened_files.append(file_path)
                
                # 启用相关操作
                self.actionEditShapes.setEnabled(True)
                self.actionFilterAllEdges.setEnabled(True)
                self.actionFilterTopLeft.setEnabled(True)
                self.actionFilterRightBottom.setEnabled(True)
                
                # 添加文件大小标签
                file_size = os.path.getsize(file_path)
                self.fileSizeLabel.setText(f"File Size: {file_size / 1024:.1f} KB; ")
                self.fit_to_view()
                
                # 添加图像大小标签
                pixmap = graphics_view.pixmap_item.pixmap()
                self.imageSizeLabel.setText(f"Image Size: {pixmap.width()}×{pixmap.height()}; ")
            else:
                if file_path in self.opened_files:
                    # 文件已经打开，切换到该标签页
                    for i in range(self.tabWidget.count()):
                        tab = self.tabWidget.widget(i)
                        if tab.property("file_path") == file_path:
                            self.tabWidget.setCurrentIndex(i)
                            
                            break

    def close_tab(self, index):
        tab = self.tabWidget.widget(index)
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
                            graphics_view.canvas.undo_stack.clear()
                        
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
            self.mousePositionLabel.setText("Mouse Position: N/A; ")
            self.pixelValueLabel.setText("Pixel Value: N/A; ")
            self.imageSizeLabel.setText("Image Size: N/A; ")
            self.fileSizeLabel.setText("File Size: N/A; ")
            
            # 禁用依赖图像的操作
            self.actionEditShapes.setEnabled(False)
            self.actionFeatureExtraction.setEnabled(False)
            self.actionGetMER.setEnabled(False)
            self.actionFilterAllEdges.setEnabled(False)
            self.actionFilterTopLeft.setEnabled(False)
            self.actionFilterRightBottom.setEnabled(False)

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
                file_path = current_tab.property("file_path")

                # 如果没有图像，显示错误
                if not file_path:
                    self.progress_dialog_aborad.accept()
                    QMessageBox.warning(self, "Error", "Currently no image is open, please open an image first.")
                    return

                # 设置模型路径
                # cls_model_path = r"Cls_best.pt"
                # 从资源文件中读取模型

                model_resource = QFile(":/Cls_best.pt")
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
                self.aborad_thread.inferenceFinished.connect(self.on_aborad_inference_finished)
                self.aborad_thread.start()

        except Exception as e:
            if hasattr(self, 'progress_dialog_aborad') and self.progress_dialog_aborad:
                self.progress_dialog_aborad.accept()
            QMessageBox.warning(self, "Error", f"An error occurred: {str(e)}")
            self._cleanup_aborad_resources()

    def on_aborad_inference_finished(self, ab_probability, ad_probability, file_path, error):
        try:
            # 关闭进度对话框
            if hasattr(self, 'progress_dialog_aborad') and self.progress_dialog_aborad:
                self.progress_dialog_aborad.update_message("Image inference AB or AD completed")
                self.progress_dialog_aborad.accept()

            if error:
                QMessageBox.warning(self, "Error", f"An error occurred during inference: {error}")
                return

            # 显示结果
            output = f'abaxial_probability: {ab_probability:.4f}%, adaxial_probability: {ad_probability:.4f}%'

            if not output.strip():
                output = "No output information was detected.(Maybe the model is not loaded correctly.)"

            # 显示在消息框中
            QMessageBox.information(self, "Result:", output)
        finally:
            # 无论如何都要清理资源
            self._cleanup_aborad_resources()

    def _cleanup_aborad_resources(self):
        """清理AB/AD推理相关的资源"""
        # 清理临时模型文件
        if hasattr(self, '_temp_model_path') and self._temp_model_path:
            try:
                if os.path.exists(self._temp_model_path):
                    os.unlink(self._temp_model_path)
                self._temp_model_path = None
            except Exception as e:
                print(f"An error occurred while cleaning the temporary model file: {e}")
        
        # 释放线程资源
        if hasattr(self, 'aborad_thread') and self.aborad_thread:
            try:
                if self.aborad_thread.isRunning():
                    self.aborad_thread.wait()
                self.aborad_thread.deleteLater()
                self.aborad_thread = None
            except Exception as e:
                print(f"An error occurred while cleaning thread resources: {e}")
        gc.collect()
        print("AB/AD inference resources cleaned up.")

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
                model_name = model_path.split('/')[-1] if '/' in model_path else model_path.split('\\')[-1]
                QMessageBox.information(self, "Model loading success",
                                        f"The model has been successfully loaded: {model_name}")
                print(f"The model has been successfully loaded: {model_path}, {self.model.model_name}")

            except Exception as e:
                QMessageBox.critical(self, "Model loading failure", f"Unable to load model: {str(e)}")

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
                    "save_path": os.path.join(os.getcwd(), "Inference_OutPut"),
                    "imgsz": 1024,
                    "max_det": 500
                }
            
            # 创建并启动推理线程
            self.yolo_thread = YOLOSegInferenceThread(self.model, file_path, self.inference_settings, self)
            self.yolo_thread.inferenceFinished.connect(self.on_inference_finished)
            self.yolo_thread.start()

        except Exception as e:
            if hasattr(self, 'progress_dialog') and self.progress_dialog:
                self.progress_dialog.accept()
            QMessageBox.critical(self, "Error", f"An error occurred: {str(e)}")
            
    ###  完成推理后的一些任务，json 文件生成，shape 类的生成在推理完成后，以及释放不再使用的变量
    ### Some tasks after completing the inference, such as generating JSON files,
    ### generating Shape classes , and releasing variables that are no longer in use.
    # 修改on_inference_finished函数
    def on_inference_finished(self, results, file_path, error):
        if error:
            QMessageBox.critical(self, "Error", f"An error occurs during the inference process: {error}")
            if hasattr(self, 'progress_dialog') and self.progress_dialog:
                self.progress_dialog.accept()
            return

        
        current_tab = self.tabWidget.currentWidget()
        graphics_view = current_tab.property("graphics_view")
        
        # 后处理进行导入shape
        self.box_shapes = []  # 存储box类型的形状，不需要线程处理
        output_dir = self.inference_settings.get("save_path", os.path.join(os.getcwd(), "Inference_OutPut"))
        os.makedirs(output_dir, exist_ok=True)
        
        # 更新进度条消息
        if hasattr(self, 'progress_dialog') and self.progress_dialog:
            self.progress_dialog.update_message("Processing the inference results...")
        
        # 记录需要处理的结果数
        self.remaining_results = len(results)
        
        has_segments = False  # 标记是否有segments类型的数据
        
        for result in results:
            json_str = result.to_json()
            json_obj = json.loads(json_str)  # 将 JSON 字符串解析为 Python 字典对象
            # 生成 JSON 文件路径：
            json_file_path = os.path.join(output_dir, f"{os.path.splitext(os.path.basename(result.path))[0]}.json")
            # 根据保存路径进行保存JSON文件
            with open(json_file_path, 'w') as json_file:
                json.dump(json_obj, json_file, indent=4)
            
            print(f'json文件保存至:{json_file_path}')  
            if json_obj in [None, {},[]]:
                QMessageBox.warning(
                self,
                "Notice",
                "The model did not return any inference results. This might be because the  confidence is too high or the model is unable to identify the target in the image."
            )
                if hasattr(self, 'progress_dialog') and self.progress_dialog:
                    self.progress_dialog.accept()
                return

            if isinstance(json_obj, list):
                current_canvas = graphics_view.canvas
                image_size = current_canvas.image_size
                image_width = image_size.width()
                image_height = image_size.height()
                
                # 直接处理box类型的项目
                class_counts = defaultdict(int)  # 用于追踪各个类别的group_id
                for item in json_obj:
                    if 'segments' not in item and 'box' in item:
                        # 处理box类型，无需线程处理
                        box = item['box']
                        x1, y1 = box.get('x1', 0), box.get('y1', 0)
                        x2, y2 = box.get('x2', 0), box.get('y2', 0)
                        top_left = QPointF(x1, y1)
                        bottom_right = QPointF(x2, y2)
                        label = item.get('name', 'undefined')
                        classnum = item.get('class', 'undefined')
                        
                        # 分配 group_id
                        group_id = class_counts[classnum]
                        class_counts[classnum] += 1
                        
                        shape = Shape(
                            label=label, 
                            classnum=classnum,
                            pointslist=[top_left, bottom_right], 
                            shape_type='rectangle', 
                            group_id=group_id,
                            scale_factor=graphics_view.canvas.scale_factor
                        )
                        self.box_shapes.append(shape)
                        # 删除这里的调用，避免循环中重复更新UI
                        # self.finish_processing_shapes(self.box_shapes)

                    elif 'segments' in item:
                        # 收集segments类型数据并按类别分组
                        has_segments = True
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
                        
                            # 只有当有多边形数据时才启动线程处理
                            if polygons_by_class:
                                # 更新进度条消息
                                if hasattr(self, 'progress_dialog') and self.progress_dialog:
                                    self.progress_dialog.update_message("Processing polygon data...")
                                
                                self.polygon_thread = PolygonProcessThread(
                                    polygons_by_class, image_width, image_height, json_obj, self)
                                self.polygon_thread.processingFinished.connect(self.on_polygon_processing_finished)
                                self.polygon_thread.start()
                                return  # 提前返回，等待线程处理完成
                    else:
                        QMessageBox.warning(self, "Error", "There is an error in the Json data structure.")
                        if hasattr(self, 'progress_dialog') and self.progress_dialog:
                            self.progress_dialog.accept()
            
            else:
                QMessageBox.warning(self, "Error", "Unknown Error Occurred During the Process of Parsing Json.")
                if hasattr(self, 'progress_dialog') and self.progress_dialog:
                    self.progress_dialog.accept()
        
        # 只有在没有segments类型数据时，才在这里处理box shapes
        if not has_segments and self.box_shapes:
            self.finish_processing_shapes(self.box_shapes)


    def on_polygon_processing_finished(self, processed_map, json_obj, error):
        if error:
            QMessageBox.warning(self, "Error", f"An error occurred during polygon processing: {error}")
            if hasattr(self, 'progress_dialog') and self.progress_dialog:
                self.progress_dialog.accept()
            return
        
        try:      
            # 获取当前的画布和视图
            current_tab = self.tabWidget.currentWidget()
            graphics_view = current_tab.property("graphics_view")
            current_canvas = graphics_view.canvas
            
            polygon_shapes = []  # 用于存储从多边形数据创建的形状
            class_counts = defaultdict(int)  # 初始化计数器
            
            # 处理多边形数据
            class_index_map = defaultdict(int)  # 用于跟踪每个类别内的索引
            
            # 处理每个json项
            for item in json_obj:
                if 'segments' in item:
                    classnum = item.get('class', 'undefined')
                    current_index = class_index_map[classnum]
                    class_index_map[classnum] += 1
                    
                    # 获取多边形坐标
                    pointslist = None
                    
                    # 尝试获取处理后的数据
                    if classnum in processed_map:
                        processed_data = processed_map[classnum]
                        
                        # 处理数据结构差异 (列表或字典)
                        if isinstance(processed_data, list) and current_index < len(processed_data):
                            x_coords, y_coords = processed_data[current_index]
                            pointslist = [QPointF(x, y) for x, y in zip(x_coords, y_coords)]
                        elif isinstance(processed_data, dict) and current_index in processed_data:
                            x_coords, y_coords = processed_data[current_index]
                            pointslist = [QPointF(x, y) for x, y in zip(x_coords, y_coords)]
                    
                    # 如果没有找到处理后的数据，使用原始数据
                    if pointslist is None:
                        x_coords = item['segments'].get('x', [])
                        y_coords = item['segments'].get('y', [])
                        if len(x_coords) == len(y_coords):  # 确保坐标数量匹配
                            pointslist = [QPointF(x, y) for x, y in zip(x_coords, y_coords)]
                        else:
                            continue  # 跳过坐标不匹配的情况
                    
                    if not pointslist:
                        continue  # 跳过空坐标的情况
                    
                    # 创建形状对象
                    label = item.get('name', 'undefined')
                    group_id = class_counts[classnum]
                    class_counts[classnum] += 1
                    
                    shape = Shape(
                        label=label, 
                        classnum=classnum,
                        pointslist=pointslist, 
                        shape_type='polygon', 
                        group_id=group_id,
                        scale_factor=graphics_view.canvas.scale_factor
                    )
                    polygon_shapes.append(shape)
            
            # 合并多边形形状和之前处理的box形状
            all_shapes = polygon_shapes 

            # 完成处理
            self.finish_processing_shapes(all_shapes)
            
        except Exception as e:
            print(f"Error in on_polygon_processing_finished: {str(e)}")
            print(traceback.format_exc())
            if hasattr(self, 'progress_dialog') and self.progress_dialog:
                self.progress_dialog.accept()
            QMessageBox.warning(self, "Error", f"处理多边形结果时出错: {str(e)}")

    # 添加一个新的辅助方法来完成处理
    def finish_processing_shapes(self, shapes):
        """完成形状处理并更新UI"""
        try:
            # 获取当前的画布
            current_tab = self.tabWidget.currentWidget()
            graphics_view = current_tab.property("graphics_view")
            current_canvas = graphics_view.canvas
            
            # 将 shapes 存储到当前标签页的canvas中
            current_canvas.shapes.extend(shapes)
            current_canvas.update()
            
            # 更新列表
            self.labeldockinstance.populate(current_canvas.shapes, Shape.get_color_by_classnum)
            self.shapedockinstance.populate(current_canvas.shapes)
            
            # 设置模式为 edit 模式
            current_canvas.set_mode('edit')
            
            # 模拟按下 edit 按钮
            self.actionEditShapes.setChecked(True)
            self.edit_shapes()
            
            # 更新进度条窗口的消息
            if hasattr(self, 'progress_dialog') and self.progress_dialog:
                self.progress_dialog.update_message("Image analysis completed")
                # 关闭进度条窗口
                self.progress_dialog.accept()
                
            self.update_actions_inToolBar()
        except Exception as e:
            print(f"Error in finish_processing_shapes: {str(e)}")
            print(traceback.format_exc())
            if hasattr(self, 'progress_dialog') and self.progress_dialog:
                self.progress_dialog.accept()
            QMessageBox.warning(self, "Error", f"完成形状处理时出错: {str(e)}")


    #################################################################
    # ↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑
    # 关于模型推理部分，有模型加载，以及调用单独的线程进行推理
    # # Regarding the model inference part, there are model loading and calling of separate threads for inference.
    #################################################################

    ####################################################################
    # 以下方法与更改显示形状的颜色相关
    # The methods are related to the modification of the color of the shape.
    ####################################################################

    def show_color_settings(self):
        try:
            current_shape = self.get_current_shapes()
            if current_shape:
                dialog = ColorSettingsDialog(self, Shape.color_map)
                if dialog.exec_() == QtWidgets.QDialog.Accepted:
                    new_color_map = dialog.get_color_map()
                    Shape.set_color_map(new_color_map)
                    # 保存颜色设置到 QSettings
                    settings = QtCore.QSettings("StomaQuant", "GUI")
                    for class_num, color in new_color_map.items():
                        settings.setValue(f"colors/class_{class_num}", color)
            
                    # 更新已经绘制的形状
                    self.update_shapes_appearance()
            else:
                QMessageBox.warning(self, "Notice", "No shapes.")
        except Exception as e:
            QMessageBox.warning(self, "Error", "Currently no image is open, please open an image first.")

    def update_shapes_appearance(self):
        """更新所有形状的外观"""
        current_canvas = self.get_current_graphics_view().canvas
        if current_canvas:
            # 标记所有形状为脏状态，确保它们会被重绘
            for shape in current_canvas.shapes:
                shape._dirty = True
            current_canvas.update()
        
        # 重新填充形状列表和标签列表，使用新的颜色设置
        if hasattr(self, 'shapedockinstance') and hasattr(self, 'labeldockinstance'):
            shapes = self.get_current_shapes()
            # 更新ShapeListDock
            self.shapedockinstance.populate(shapes)
            # 更新LabelListDock
            self.labeldockinstance.populate(shapes, Shape.get_color_by_classnum)
            
        # 更新形状列表和标签列表的显示
        self.update_shapes_and_label_list()
        
    def load_color_settings(self):
        """从 QSettings 加载颜色设置"""
        settings = QtCore.QSettings("StomaQuant", "GUI")
        color_map = {}
        
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
            except (IndexError, ValueError) as e:
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
                    self.feature_extraction_of_all_shapes()
                else:
                    return
            
            # 创建并显示热图对话框
            dialog = HeatMapDialog(self)
            if dialog.exec_() == QtWidgets.QDialog.Accepted:
                settings = dialog.get_settings()
                feature_name = settings["feature"]
                colormap_name = settings["colormap"]
                output_path = settings["output_path"]
                scale_info = settings.get("scale_info")  # 获取比例尺信息
                
                if not output_path:
                    QtWidgets.QMessageBox.warning(self, "Noticce", "Please select the save path.")
                    return
                
                # 显示进度对话框
                self.progress_dialog_heatmap = ProgressDialog(self)
                self.progress_dialog_heatmap.update_message(f"Generating a heatmap based on {feature_name} is in progress....")
                self.progress_dialog_heatmap.show()
                QtWidgets.QApplication.processEvents()
                
                # 获取图像副本
                current_pixmap = current_view.pixmap_item.pixmap()
                image = current_pixmap.toImage()
                current_tab = self.tabWidget.currentWidget()
                file_path = current_tab.property("file_path") if current_tab else ""
            
                # 创建并启动热图生成线程
                
                # 创建并启动热图生成线程
                self.heatmap_thread = HeatMapGenerationThread(
                    image, shapes, feature_name, colormap_name, output_path, file_path, scale_info, self
                )
                self.heatmap_thread.heatmapGenerated.connect(self.on_heatmap_generated)
                self.heatmap_thread.start()


        
        except Exception as e:
            import traceback
            print(f"Error occurred when displaying the heatmap dialog box: {str(e)}")
            print(traceback.format_exc())
            QtWidgets.QMessageBox.critical(self, "Error", f"An error occurred while executing the heatmap function：{str(e)}")
            if hasattr(self, 'progress_dialog_heatmap'):
                self.progress_dialog_heatmap.accept()

    def on_heatmap_generated(self, file_path, error):
        """热图生成完成后的回调"""
        if hasattr(self, 'progress_dialog_heatmap'):
            self.progress_dialog_heatmap.accept()
        
        if error:
            QtWidgets.QMessageBox.warning(self, "Error", f"An error occurred while generating the heatmap: {error}")
        elif file_path:
            QtWidgets.QMessageBox.information(
                self, 
                "Saved successfully",
                f"The heatmap generation was successful and saved to:\n{file_path}."
            )
        else:
            QtWidgets.QMessageBox.warning(self, "Error", "An unknown error occurred during the generation of the heatmap.")

    ####################################################################
    # 以下方法多边形/正方形注释的保存或者导入相关
    # Save or Import Polygon/(Rotated) Rectangle Annotation Methods Related to This
    # ↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓
    ####################################################################

    def import_polygon(self):
        # Check if an image is open
        current_tab = self.tabWidget.currentWidget()
        if not current_tab:
            QMessageBox.warning(self, "Notice", "Please open an image file first.")
            return

        # Open file dialog to select txt file
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Import Annotation File", "", "Text Files (*.txt);;All Files (*)")

        if not file_path:
            return  # User cancelled operation

        try:
            # Get canvas and image dimensions
            current_canvas = self.get_current_graphics_view().canvas
            image_size = current_canvas.image_size
            image_width = image_size.width()
            image_height = image_size.height()

            # Save current state for undo support
            current_canvas.save_state()
            
            # Temporarily block signals - key optimization
            current_canvas.blockSignals(True)

            # Read file content and parse
            with open(file_path, 'r') as f:
                lines = f.readlines()

            # Create progress dialog
            progress = QProgressDialog("Importing polygon annotations...", "Cancel", 0, len(lines), self)
            progress.setWindowModality(Qt.WindowModal)
            progress.setMinimumDuration(500)  # Only show if operation takes more than 500ms
            
            imported_count = 0
            shapes_to_add = []  # Collect all shapes before adding them at once - key optimization
            
            # Group by class, to correctly assign group_id for each class
            class_to_max_group_id = {}
            
            for i, line in enumerate(lines):
                if progress.wasCanceled():
                    break
                    
                progress.setValue(i)
                QApplication.processEvents()  # Ensure UI remains responsive
                
                parts = line.strip().split()
                if len(parts) < 5 or len(parts) % 2 == 0:  # Need at least class_id and two points
                    continue

                try:
                    classnum = int(parts[0])
                    points = []

                    # Parse coordinates and convert back to pixel coordinates
                    for i in range(1, len(parts), 2):
                        if i + 1 < len(parts):
                            x = float(parts[i]) * image_width
                            y = float(parts[i + 1]) * image_height
                            points.append(QPointF(x, y))

                    if len(points) < 3:  # Polygon needs at least 3 points
                        continue

                    # Determine group_id - find maximum group_id with same classnum and add 1
                    if classnum not in class_to_max_group_id:
                        # Initialize maximum group_id for this class
                        max_group_id = -1
                        for shape in current_canvas.shapes:
                            if shape.classnum == classnum and shape.group_id > max_group_id:
                                max_group_id = shape.group_id
                        class_to_max_group_id[classnum] = max_group_id
                    
                    # Assign new group_id
                    class_to_max_group_id[classnum] += 1
                    group_id = class_to_max_group_id[classnum]

                    # Create new shape
                    new_shape = Shape(
                        label=f"Class {classnum}",  # Default label
                        classnum=classnum,
                        pointslist=points,
                        shape_type='polygon',
                        group_id=group_id
                    )

                    # Collect shape
                    shapes_to_add.append(new_shape)
                    imported_count += 1

                except (ValueError, IndexError) as e:
                    print(f"Error parsing line: {line}, Error: {e}")
                    continue
            
            progress.setValue(len(lines))
            
            # Add all shapes at once - key optimization
            if shapes_to_add:
                # Use extend to add all shapes at once
                current_canvas.shapes.extend(shapes_to_add)
            
            # Restore signals and update once - key optimization
            current_canvas.blockSignals(False)
            current_canvas.update()
            current_canvas.shapesChanged.emit()
            self.update_shapes_and_label_list()

            if imported_count > 0:
                QMessageBox.information(self, "Import Success", f"Successfully imported {imported_count} polygon annotations")
            else:
                QMessageBox.warning(self, "Warning", "No polygon annotations were imported.")

        except Exception as e:
            QMessageBox.critical(self, "Error", f"An error occurred when importing the annotation file: {str(e)}")
    
    def import_rectangle(self):
        # Check if an image is open
        current_tab = self.tabWidget.currentWidget()
        if not current_tab:
            QMessageBox.warning(self, "Notice", "Please open an image file first.")
            return

        # Open file dialog to select txt file
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Import Rectangle Annotation File", "", "Text Files (*.txt);;All Files (*)")

        if not file_path:
            return  # User cancelled operation

        try:
            # Get canvas and image dimensions
            current_canvas = self.get_current_graphics_view().canvas
            image_size = current_canvas.image_size
            image_width = image_size.width()
            image_height = image_size.height()

            # Save current state for undo support
            current_canvas.save_state()
            
            # Temporarily block signals - key optimization
            current_canvas.blockSignals(True)

            # Read file content and parse
            with open(file_path, 'r') as f:
                lines = f.readlines()

            # Create progress dialog
            progress = QProgressDialog("Importing rectangle annotations...", "Cancel", 0, len(lines), self)
            progress.setWindowModality(Qt.WindowModal)
            progress.setMinimumDuration(500)  # Only show if operation takes more than 500ms
            
            imported_count = 0
            shapes_to_add = []  # Collect all shapes before adding them at once
            
            # Group by class, to correctly assign group_id for each class
            class_to_max_group_id = {}
            
            for i, line in enumerate(lines):
                if progress.wasCanceled():
                    break
                    
                progress.setValue(i)
                QApplication.processEvents()  # Ensure UI remains responsive
                
                parts = line.strip().split()
                if len(parts) != 5:  # YOLO format: class x_center y_center width height
                    continue

                try:
                    classnum = int(parts[0])
                    x_center = float(parts[1]) * image_width
                    y_center = float(parts[2]) * image_height
                    width = float(parts[3]) * image_width
                    height = float(parts[4]) * image_height

                    # Calculate top-left and bottom-right coordinates
                    x1 = x_center - width / 2
                    y1 = y_center - height / 2
                    x2 = x_center + width / 2
                    y2 = y_center + height / 2

                    # Create two points: top-left and bottom-right
                    top_left = QPointF(x1, y1)
                    bottom_right = QPointF(x2, y2)

                    # Determine group_id - find maximum group_id with same classnum and add 1
                    if classnum not in class_to_max_group_id:
                        # Initialize maximum group_id for this class
                        max_group_id = -1
                        for shape in current_canvas.shapes:
                            if shape.classnum == classnum and shape.group_id > max_group_id:
                                max_group_id = shape.group_id
                        class_to_max_group_id[classnum] = max_group_id
                    
                    # Assign new group_id
                    class_to_max_group_id[classnum] += 1
                    group_id = class_to_max_group_id[classnum]

                    # Create new shape
                    new_shape = Shape(
                        label=f"Class {classnum}",  # Default label
                        classnum=classnum,
                        pointslist=[top_left, bottom_right],
                        shape_type='rectangle',
                        group_id=group_id
                    )

                    # Collect shape
                    shapes_to_add.append(new_shape)
                    imported_count += 1

                except (ValueError, IndexError) as e:
                    print(f"Error parsing line: {line}, Error: {e}")
                    continue
            
            progress.setValue(len(lines))
            
            # Add all shapes at once - key optimization
            if shapes_to_add:
                # Use extend to add all shapes at once
                current_canvas.shapes.extend(shapes_to_add)
            
            # Restore signals and update once - key optimization
            current_canvas.blockSignals(False)
            current_canvas.update()
            current_canvas.shapesChanged.emit()
            self.update_shapes_and_label_list()

            if imported_count > 0:
                QMessageBox.information(self, "Import Success", f"Successfully imported {imported_count} rectangle annotations")
            else:
                QMessageBox.warning(self, "Warning", "No rectangle annotations were imported.")

        except Exception as e:
            QMessageBox.critical(self, "Error", f"An error occurred when importing the annotation file: {str(e)}")
    
    def import_rotated_rectangle(self):
        # Check if an image is open
        current_tab = self.tabWidget.currentWidget()
        if not current_tab:
            QMessageBox.warning(self, "Notice", "Please open an image file first.")
            return

        # Open file dialog to select txt file
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Import Rotated Rectangle Annotation", "", "Text Files (*.txt);;All Files (*)")

        if not file_path:
            return  # User cancelled operation

        try:
            # Get canvas and image dimensions
            current_canvas = self.get_current_graphics_view().canvas
            image_size = current_canvas.image_size
            image_width = image_size.width()
            image_height = image_size.height()

            # Save current state for undo support
            current_canvas.save_state()
            
            # Temporarily block signals - key optimization
            current_canvas.blockSignals(True)

            # Read file content and parse
            with open(file_path, 'r') as f:
                lines = f.readlines()

            # Create progress dialog
            progress = QProgressDialog("Importing rotated rectangle annotations...", "Cancel", 0, len(lines), self)
            progress.setWindowModality(Qt.WindowModal)
            progress.setMinimumDuration(500)  # Only show if operation takes more than 500ms
            
            imported_count = 0
            shapes_to_add = []  # Collect all shapes before adding them at once
            
            # Group by class, to correctly assign group_id for each class
            class_to_max_group_id = {}
            
            for i, line in enumerate(lines):
                if progress.wasCanceled():
                    break
                    
                progress.setValue(i)
                QApplication.processEvents()  # Ensure UI remains responsive
                
                parts = line.strip().split()
                if len(parts) != 9:  # OBB format: class x1 y1 x2 y2 x3 y3 x4 y4
                    continue

                try:
                    classnum = int(parts[0])
                    points = []

                    # Parse four points' coordinates and convert back to pixel coordinates
                    for i in range(1, 9, 2):
                        x = float(parts[i]) * image_width
                        y = float(parts[i + 1]) * image_height
                        points.append(QPointF(x, y))

                    if len(points) != 4:  # Ensure there are 4 points
                        continue

                    # Determine group_id - find maximum group_id with same classnum and add 1
                    if classnum not in class_to_max_group_id:
                        # Initialize maximum group_id for this class
                        max_group_id = -1
                        for shape in current_canvas.shapes:
                            if shape.classnum == classnum and shape.group_id > max_group_id:
                                max_group_id = shape.group_id
                        class_to_max_group_id[classnum] = max_group_id
                    
                    # Assign new group_id
                    class_to_max_group_id[classnum] += 1
                    group_id = class_to_max_group_id[classnum]

                    # Create new shape
                    new_shape = Shape(
                        label=f"Class {classnum}",  # Default label
                        classnum=classnum,
                        pointslist=points,
                        shape_type='rotated_rectangle',
                        group_id=group_id
                    )

                    # Collect shape
                    shapes_to_add.append(new_shape)
                    imported_count += 1

                except (ValueError, IndexError) as e:
                    print(f"Error parsing line: {line}, Error: {e}")
                    continue
            
            progress.setValue(len(lines))
            
            # Add all shapes at once - key optimization
            if shapes_to_add:
                # Use extend to add all shapes at once
                current_canvas.shapes.extend(shapes_to_add)
            
            # Restore signals and update once - key optimization
            current_canvas.blockSignals(False)
            current_canvas.update()
            current_canvas.shapesChanged.emit()
            self.update_shapes_and_label_list()

            if imported_count > 0:
                QMessageBox.information(self, "Import Success", f"Successfully imported {imported_count} rotated rectangle annotations")
            else:
                QMessageBox.warning(self, "Warning", "No rotated rectangle annotations were imported.")

        except Exception as e:
            QMessageBox.critical(self, "Error", f"An error occurred when importing the annotation file: {str(e)}")
    
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
            with open(file_path, 'w') as f:
                for shape in current_shapes:
                    # 只处理polygon类型
                    if shape.shape_type != 'polygon' or not shape.visible:
                        continue
                    # YOLO格式:类别编号 x1 y1 x2 y2 x3 y3...
                    points = []
                    # 添加类别编号
                    points.append(str(shape.classnum))
                    # 获取图片尺寸用于归一化坐标
                    current_canvas = self.get_current_graphics_view().canvas
                    image_size = current_canvas.image_size
                    image_width = image_size.width()
                    image_height = image_size.height()
                    # 添加归一化后的坐标点
                    for point in shape.pointslist:
                        x = point.x() / image_width
                        y = point.y() / image_height
                        points.extend([f"{x:.6f}", f"{y:.6f}"])
                    # 写入一行
                    f.write(' '.join(points) + '\n')

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
            with open(file_path, 'w') as f:
                for shape in current_shapes:
                    # 只处理rectangle类型
                    if shape.shape_type != 'rectangle' or not shape.visible:
                        continue

                    # 获取图片尺寸用于归一化坐标
                    current_canvas = self.get_current_graphics_view().canvas
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
            with open(file_path, 'w') as f:
                for shape in current_shapes:
                    # 只处理rotated_rectangle类型
                    if shape.shape_type != 'rotated_rectangle' or not shape.visible:
                        continue

                    # 获取图片尺寸用于归一化坐标
                    current_canvas = self.get_current_graphics_view().canvas
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
                        line += f" {x:.6f} {y:.6f}"

                    line += "\n"
                    f.write(line)

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
        current_canvas = self.get_current_graphics_view().canvas
        image_size = current_canvas.image_size
        image_width = image_size.width()
        image_height = image_size.height()
        tolerance = 3  # 设定贴近边界的容差（可以根据需要调整）

        shapes_to_delete = []

        for shape in current_canvas.shapes:
            bounding_rect = shape.get_bounding_rect()
            if (bounding_rect.left() <= tolerance or
                    bounding_rect.right() >= image_width - tolerance or
                    bounding_rect.top() <= tolerance or
                    bounding_rect.bottom() >= image_height - tolerance):
                shapes_to_delete.append(shape)

        if shapes_to_delete:
            current_canvas.save_state()  # 保存当前状态以支持撤销
            for shape in shapes_to_delete:
                current_canvas.shapes.remove(shape)
            current_canvas.update()
            current_canvas.shapesChanged.emit()
            self.update_canvas()
            self.update_shapes_and_label_list()  # 更新列表显示
        print("All edges filter applied.")

    def shape_TopLeft_filter(self):
        current_canvas = self.get_current_graphics_view().canvas
        image_size = current_canvas.image_size
        # image_width = image_size.width()
        # image_height = image_size.height()
        tolerance = 3  # 设定贴近边界的容差

        shapes_to_delete = []

        for shape in current_canvas.shapes:
            bounding_rect = shape.get_bounding_rect()
            if (bounding_rect.left() <= tolerance or
                    bounding_rect.top() <= tolerance):
                shapes_to_delete.append(shape)

        if shapes_to_delete:
            current_canvas.save_state()
            for shape in shapes_to_delete:
                current_canvas.shapes.remove(shape)
            current_canvas.update()
            current_canvas.shapesChanged.emit()
            self.update_canvas()
            self.update_shapes_and_label_list()  # 更新列表显示
        print("TopLeft filter applied.")

    def shape_RightBottom_filter(self):
        current_canvas = self.get_current_graphics_view().canvas
        image_size = current_canvas.image_size
        image_width = image_size.width()
        image_height = image_size.height()
        tolerance = 3  # 设定贴近边界的容差

        shapes_to_delete = []

        for shape in current_canvas.shapes:
            bounding_rect = shape.get_bounding_rect()
            if (bounding_rect.right() >= image_width - tolerance or
                    bounding_rect.bottom() >= image_height - tolerance):
                shapes_to_delete.append(shape)

        if shapes_to_delete:
            current_canvas.save_state()
            for shape in shapes_to_delete:
                current_canvas.shapes.remove(shape)
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
        canvas = self.get_current_graphics_view().canvas
        if canvas.selected_shape:
            canvas.save_state()

            # 创建副本以避免迭代时修改
            selected_to_delete = canvas.selected_shape.copy()

            for shape in selected_to_delete:
                # 使用Canvas类的remove_shape方法完全移除形状
                if shape in canvas.shapes:
                    # 确保在删除前，形状引用正确的场景
                    canvas.remove_shape(shape)
                    shape.update_shape()

            # 确保清空选择列表和其他引用
            canvas.selected_shape = []

            self.update_shapes_and_label_list()  # 更新列表显示

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
                # 保存当前状态以支持撤销
                canvas.save_state()

                # 暂时禁止画布发送信号和更新
                canvas.blockSignals(True)

                # 创建可见形状的副本以避免迭代时修改列表
                visible_shapes = [shape for shape in canvas.shapes if shape.visible]

                # 使用canvas的remove_shape方法正确删除每个形状
                for shape in visible_shapes:
                    canvas.remove_shape(shape)

                # 清空选择
                canvas.selected_shape = []

                # 恢复信号发送和更新
                canvas.blockSignals(False)
                canvas.update()

                # 一次性更新列表
                self.update_shapes_and_label_list()
                
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
    app.setWindowIcon(app_icon)
    font = QFont("微软雅黑", 10)
    app.setFont(font)

    try:
        # 创建启动画面
        splash_pix = QPixmap(":/Start_up.png")  # 替换为你的启动画面图片路径
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


