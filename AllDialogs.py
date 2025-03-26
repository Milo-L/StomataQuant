from PyQt5 import QtCore, QtGui, QtWidgets
from PyQt5.QtCore import QEventLoop, QPropertyAnimation, QRect, QEasingCurve, Qt, QTimer, pyqtProperty
from PyQt5.QtGui import QBrush, QColor, QImage, QPainter, QPixmap
from PyQt5.QtWidgets import (QCheckBox, QComboBox, QDialog, QFileDialog, QHBoxLayout, QLabel, QLineEdit,
                             QMessageBox, QProgressBar, QPushButton, QVBoxLayout, QWidget, QButtonGroup)
import matplotlib.pyplot as plt
from matplotlib.colors import LinearSegmentedColormap
import numpy as np
import os
import tempfile



from PyQt5.QtWidgets import (QDialog, QVBoxLayout, QCheckBox, QPushButton, QGroupBox, 
                            QRadioButton, QHBoxLayout, QLabel, QProgressBar, QDialogButtonBox,
                            QApplication, QMessageBox, QFileDialog)
from PyQt5.QtCore import Qt, QTimer, QEventLoop
import os
import time

class BatchProcessingDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent = parent  # 保存父窗口引用
        self.setWindowTitle("Batch Processing Options")
        self.resize(450, 400)  # 增加对话框高度以适应新内容
        
        layout = QVBoxLayout()
        
        # 添加当前打开的标签页数量信息
        tab_count = self.parent.tabWidget.count() if self.parent and hasattr(self.parent, 'tabWidget') else 0
        self.tab_info_label = QLabel(f"The current number of open images: {tab_count}")
        self.tab_info_label.setStyleSheet("font-weight: bold; margin-bottom: 5px;")
        layout.addWidget(self.tab_info_label)
        
        # 添加操作选择提示
        self.operation_guide_label = QLabel("Select the operation to be performed on all images:")
        layout.addWidget(self.operation_guide_label)
        
        # YOLO Segmentation
        self.ai_checkbox = QCheckBox("Run YOLO ")
        # 在上面代码后添加:
        # self.ai_checkbox.setChecked(True)  # 默认选中
        layout.addWidget(self.ai_checkbox)
        # 创建一个水平布局，包含模型信息标签和更换模型按钮
        model_info_layout = QHBoxLayout()
        
        # 模型信息显示
        self.model_info_label = QLabel("Model: Not loaded")
        self.model_info_label.setStyleSheet("color: gray; margin-left: 20px;")
        model_info_layout.addWidget(self.model_info_label)

        # 添加更换模型按钮
        self.change_model_button = QPushButton("Change the model")
        self.change_model_button.clicked.connect(self.change_model)
        model_info_layout.addWidget(self.change_model_button)
    
        model_info_layout.addStretch()  # 添加伸缩空间，使控件靠左对齐
        layout.addLayout(model_info_layout)
        
        # 添加推理设置按钮
        self.inference_settings_button = QPushButton("Inference Settings")
        self.inference_settings_button.clicked.connect(self.open_inference_settings)
        inference_button_layout = QHBoxLayout()
        inference_button_layout.addSpacing(20)  # 添加缩进
        inference_button_layout.addWidget(self.inference_settings_button)
        inference_button_layout.addStretch()  # 让按钮不要占据整行
        layout.addLayout(inference_button_layout)
        
        # 检查并更新模型信息
        self.update_model_info()
        
        # Filter options (radio buttons in a group)
        filter_group = QGroupBox("Filter Options")
        filter_layout = QVBoxLayout()
        self.no_filter_radio = QRadioButton("No Filter")
        self.all_edges_radio = QRadioButton("Filter All Edges")
        self.top_left_radio = QRadioButton("Filter Top-Left Edges")
        self.right_bottom_radio = QRadioButton("Filter Right-Bottom Edges")
        
        self.no_filter_radio.setChecked(True)
        
        filter_layout.addWidget(self.no_filter_radio)
        filter_layout.addWidget(self.all_edges_radio)
        filter_layout.addWidget(self.top_left_radio)
        filter_layout.addWidget(self.right_bottom_radio)
        filter_group.setLayout(filter_layout)
        layout.addWidget(filter_group)

                # 添加类别可见性设置选项组 - 新增代码开始
        class_visibility_group = QGroupBox("Set label visibility")
        class_visibility_layout = QVBoxLayout()

        # ClassNum 0 行
        class_num_0_layout = QHBoxLayout()
        class_num_0_label = QLabel("Class num 0 (stoma):")
        self.class_num_0_radio_group = QButtonGroup(self)
        self.class_num_0_true = QRadioButton("True")
        self.class_num_0_false = QRadioButton("False")
        self.class_num_0_radio_group.addButton(self.class_num_0_true)
        self.class_num_0_radio_group.addButton(self.class_num_0_false)
        self.class_num_0_true.setChecked(True)  # 默认选择 True
        class_num_0_layout.addWidget(class_num_0_label)
        class_num_0_layout.addWidget(self.class_num_0_true)
        class_num_0_layout.addWidget(self.class_num_0_false)
        class_visibility_layout.addLayout(class_num_0_layout)

        # ClassNum 1 行
        class_num_1_layout = QHBoxLayout()
        class_num_1_label = QLabel("Class num 1 (pore or pavement cell):")
        self.class_num_1_radio_group = QButtonGroup(self)
        self.class_num_1_true = QRadioButton("True")
        self.class_num_1_false = QRadioButton("False")
        self.class_num_1_radio_group.addButton(self.class_num_1_true)
        self.class_num_1_radio_group.addButton(self.class_num_1_false)
        self.class_num_1_true.setChecked(True)  # 默认选择 True
        class_num_1_layout.addWidget(class_num_1_label)
        class_num_1_layout.addWidget(self.class_num_1_true)
        class_num_1_layout.addWidget(self.class_num_1_false)
        class_visibility_layout.addLayout(class_num_1_layout)

        class_visibility_group.setLayout(class_visibility_layout)
        layout.addWidget(class_visibility_group)

        # # 只有当选择了过滤器选项时才启用类别可见性设置
        # class_visibility_group.setEnabled(False)
        # self.all_edges_radio.toggled.connect(lambda checked: class_visibility_group.setEnabled(checked or self.top_left_radio.isChecked() or self.right_bottom_radio.isChecked()))
        # self.top_left_radio.toggled.connect(lambda checked: class_visibility_group.setEnabled(checked or self.all_edges_radio.isChecked() or self.right_bottom_radio.isChecked()))
        # self.right_bottom_radio.toggled.connect(lambda checked: class_visibility_group.setEnabled(checked or self.all_edges_radio.isChecked() or self.top_left_radio.isChecked()))
        # self.no_filter_radio.toggled.connect(lambda checked: class_visibility_group.setEnabled(not checked and (self.all_edges_radio.isChecked() or self.top_left_radio.isChecked() or self.right_bottom_radio.isChecked())))
        # # 新增代码结束


        # Group ID Display Options
        group_id_group = QGroupBox("Group ID Display Options")
        group_id_layout = QVBoxLayout()
        self.hide_group_id_radio = QRadioButton("Hide Group ID")
        self.show_group_id_radio = QRadioButton("Show Group ID")
        
        self.hide_group_id_radio.setChecked(True)
        
        group_id_layout.addWidget(self.hide_group_id_radio)
        group_id_layout.addWidget(self.show_group_id_radio)
        group_id_group.setLayout(group_id_layout)
        layout.addWidget(group_id_group)
        
        # 添加互斥操作选项
        self.show_points_checkbox = QCheckBox("Convert Shapes to Points")
        layout.addWidget(self.show_points_checkbox)
        
# 在 BatchProcessingDialog 类的 __init__ 方法中的 mer_checkbox 后面添加

        # Get MER
        self.mer_checkbox = QCheckBox("Get Minimum Enclosing Rectangle (MER)")
        layout.addWidget(self.mer_checkbox)

        # 添加隐藏原始多边形的选项组 - 新增代码开始
        self.hide_polygons_group = QGroupBox("Hide The original polygons")
        hide_polygons_layout = QHBoxLayout()
        self.hide_polygons_yes = QRadioButton("Yes")
        self.hide_polygons_no = QRadioButton("No")
        self.hide_polygons_no.setChecked(True)  # 默认选择"No"
        hide_polygons_layout.addWidget(self.hide_polygons_yes)
        hide_polygons_layout.addWidget(self.hide_polygons_no)
        self.hide_polygons_group.setLayout(hide_polygons_layout)
        layout.addWidget(self.hide_polygons_group)

        # 初始状态下禁用选项组，只有选中MER时才启用
        self.hide_polygons_group.setEnabled(False)
        self.mer_checkbox.stateChanged.connect(self.update_hide_polygons_group)
        # 新增代码结束

        # Feature Extraction
        self.feature_extraction_checkbox = QCheckBox("Feature Extraction")
        layout.addWidget(self.feature_extraction_checkbox)

        # 添加全局比例尺选项
        self.global_scale_checkbox = QCheckBox("Use global scale for all images (if available)")
        has_global_scale = parent and hasattr(parent, 'global_scale_info') and parent.global_scale_info

        # 如果有全局比例尺，显示比例尺信息并强制选中且不可更改
        if has_global_scale:
            scale = parent.global_scale_info.get('scale', 1.0)
            unit = parent.global_scale_info.get('unit', 'pixel')
            self.global_scale_checkbox.setText(f"Use global scale for all images (1 pixel = {scale} {unit})")
            self.global_scale_checkbox.setChecked(True)
            # 设置样式，让用户知道这个复选框是强制选中的
            self.global_scale_checkbox.setStyleSheet("QCheckBox::indicator { background-color: #e0f0e0; }")
            # 创建标志，表示这是强制选中的
            self.force_global_scale = True
        else:
            self.global_scale_checkbox.setText("Use global scale for all images (not set)")
            self.global_scale_checkbox.setEnabled(False)
            self.force_global_scale = False
                
        self.feature_extraction_checkbox.stateChanged.connect(self.on_feature_extraction_checked)
        layout.addWidget(self.global_scale_checkbox)
        
        # Heat Map
        self.heatmap_checkbox = QCheckBox("Generate Heat Map")
        layout.addWidget(self.heatmap_checkbox)
        
        # Buttons
        button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)
        
        self.setLayout(layout)
        
        # 连接热图复选框的状态变化信号
        self.heatmap_checkbox.stateChanged.connect(self.on_heatmap_checked)
        
        # 连接互斥选项信号
        self.show_points_checkbox.stateChanged.connect(self.handle_mutual_exclusion)
        self.mer_checkbox.stateChanged.connect(self.handle_mutual_exclusion)
        self.heatmap_checkbox.stateChanged.connect(self.handle_mutual_exclusion)
        
        # 添加热图设置相关的属性
        self.heatmap_settings = None
    
    def change_model(self):
        """打开模型选择对话框"""
        if hasattr(self.parent, 'load_model'):
            self.parent.load_model()
            # 延迟更新模型信息，确保模型加载完成
            QTimer.singleShot(500, self.update_model_info)

    def update_model_info(self):
        """更新模型信息显示"""
        if hasattr(self.parent, 'model') and self.parent.model:
            # 获取模型名称
            if hasattr(self.parent.model, 'model_name'):
                model_name = self.parent.model.model_name
            else:
                model_name = "Unknown Model"
            self.model_info_label.setText(f"Model: {model_name}")
            self.model_info_label.setStyleSheet("color: green; margin-left: 20px;")
            self.inference_settings_button.setEnabled(True)
        else:
            self.model_info_label.setText("Model: Not loaded")
            self.model_info_label.setStyleSheet("color: red; margin-left: 20px;")
            self.inference_settings_button.setEnabled(False)
            self.ai_checkbox.setChecked(False)
            self.ai_checkbox.setEnabled(False)
    def on_feature_extraction_checked(self, state):
        """处理特征提取复选框的状态变化"""
        # 如果有全局比例尺信息，根据特征提取复选框的状态启用/禁用全局比例尺复选框
        has_global_scale = self.parent and hasattr(self.parent, 'global_scale_info') and self.parent.global_scale_info
        if has_global_scale:
            self.global_scale_checkbox.setEnabled(state == Qt.Checked)
        else:
            self.global_scale_checkbox.setEnabled(False)
        
        # 如果取消了特征提取，同时取消热图选项
        if state == Qt.Unchecked and self.heatmap_checkbox.isChecked():
            self.heatmap_checkbox.setChecked(False)
    def open_inference_settings(self):
        """打开推理设置对话框"""
        if hasattr(self.parent, 'show_inference_settings'):
            self.parent.show_inference_settings()
    
    def on_heatmap_checked(self, state):
        """处理热图复选框的勾选状态变化"""
        if state == Qt.Checked:
            # 如果选中了热图功能，先检查是否勾选了特征提取
            if not self.feature_extraction_checkbox.isChecked():
                # 询问用户是否同时启用特征提取
                reply = QMessageBox.question(
                    self,
                    "Notice",
                    "Generating a heatmap requires feature extraction to be performed first. Do you want to enable feature extraction simultaneously?",
                    QMessageBox.Yes | QMessageBox.No,
                    QMessageBox.Yes
                )
                if reply == QMessageBox.Yes:
                    self.feature_extraction_checkbox.setChecked(True)
                else:
                    self.heatmap_checkbox.setChecked(False)
                    return
            
            # 查找主窗口，以获取其全局比例尺信息
            # 查找主窗口，以获取其全局比例尺信息
            main_window = self.parent
            while main_window and not hasattr(main_window, 'tabWidget'):
                if hasattr(main_window, 'parent'):
                    # 修复: 安全地获取父对象，同时处理属性和方法两种情况
                    parent_attr = getattr(main_window, 'parent')
                    if callable(parent_attr):
                        try:
                            main_window = parent_attr()
                        except:
                            main_window = None
                    else:
                        main_window = parent_attr
                else:
                    main_window = None
                        
            # 检查是否有全局比例尺信息（对于需要比例尺的特征）
            has_global_scale = False
            if main_window and hasattr(main_window, 'global_scale_info') and main_window.global_scale_info:
                has_global_scale = True
            
            # 打开热图设置对话框
            dialog = HeatMapDialog(self)
            if dialog.exec_() == QDialog.Accepted:
                self.heatmap_settings = dialog.get_settings()
                
                # 检查是否在热图对话框中设置了新的比例尺信息
                if dialog.scale_info:
                    # 如果是全局比例尺，也更新到主窗口
                    if hasattr(dialog, 'scale_info') and dialog.scale_info.get('is_global', False):
                        if main_window and hasattr(main_window, 'global_scale_info'):
                            main_window.global_scale_info = dialog.scale_info
                            # 更新本对话框的全局比例尺显示
                            has_global_scale = True
                            scale = dialog.scale_info.get('scale', 1.0)
                            unit = dialog.scale_info.get('unit', 'pixel')
                            self.global_scale_checkbox.setText(f"Use global scale for all images (1 pixel = {scale} {unit})")
                            self.global_scale_checkbox.setChecked(True)
                            self.global_scale_checkbox.setEnabled(True)
                
                # 检查选择的特征是否需要比例尺，但没有设置比例尺
                feature_name = self.heatmap_settings.get("feature", "")
                needs_scale = feature_name in ["Area", "Perimeter", "MER Length", "MER Width"]
                
                if needs_scale and not has_global_scale:
                    reply = QMessageBox.warning(
                        self,
                        "Scale Warning",
                        f" The feature '{feature_name}' you have selected requires scale information, but no global scale has been set at present. \n\n"
                        "Batch processing will use pixel units. Do you want to proceed?" ,
                        QMessageBox.Yes | QMessageBox.No,
                        QMessageBox.No
                    )
                    if reply == QMessageBox.No:
                        self.heatmap_checkbox.setChecked(False)
                        return
            else:
                # 用户取消了热图设置，取消勾选
                self.heatmap_checkbox.setChecked(False)
    
    # 在 BatchProcessingDialog 类中添加这个新方法

    def update_hide_polygons_group(self, state):
        """根据MER复选框状态启用或禁用隐藏多边形选项组"""
        self.hide_polygons_group.setEnabled(state == Qt.Checked)

    # 修改 get_options 方法，添加新的选项

    def get_options(self):
        options = {
            "ai": self.ai_checkbox.isChecked(),
            "filter": None,
            "group_id_display": "show" if self.show_group_id_radio.isChecked() else "hide",
            "show_points": self.show_points_checkbox.isChecked(),
            "mer": self.mer_checkbox.isChecked(),
            "hide_original_polygons": self.hide_polygons_yes.isChecked(),
            "feature_extraction": self.feature_extraction_checkbox.isChecked(),
            "heatmap": self.heatmap_checkbox.isChecked(),
            "heatmap_settings": self.heatmap_settings,
            # 添加类别可见性设置 - 新增代码
            "class_visibility": {
                0: self.class_num_0_true.isChecked(),
                1: self.class_num_1_true.isChecked()
            }
        }
        
        if self.all_edges_radio.isChecked():
            options["filter"] = "all_edges"
        elif self.top_left_radio.isChecked():
            options["filter"] = "top_left"
        elif self.right_bottom_radio.isChecked():
            options["filter"] = "right_bottom"
        
        return options
        
    def handle_mutual_exclusion(self, state):
        """处理互斥选项的逻辑"""
        sender = self.sender()
        
        # 如果是显示点被选中
        if sender == self.show_points_checkbox and state == Qt.Checked:
            self.mer_checkbox.setChecked(False)
            self.heatmap_checkbox.setChecked(False)
        
        # 如果是MER被选中
        elif sender == self.mer_checkbox and state == Qt.Checked:
            self.show_points_checkbox.setChecked(False)
        
        # 如果是热图被选中
        elif sender == self.heatmap_checkbox and state == Qt.Checked:
            self.show_points_checkbox.setChecked(False)
class BatchProgressDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Batch Processing Progress")
        self.resize(550, 200)
        self.setModal(True)

        # 移除窗口的关闭按钮
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowCloseButtonHint)
        
        layout = QVBoxLayout()
        
        self.tab_label = QLabel("Processing tab: 0/0")
        layout.addWidget(self.tab_label)
        
        # Operation label
        self.operation_label = QLabel("Operation: Preparing...")
        layout.addWidget(self.operation_label)
        
        # File label
        self.file_label = QLabel("File: Waiting...")
        layout.addWidget(self.file_label)
        
        # Progress bar for current operation
        self.operation_progress_label = QLabel("Operation Progress:")
        layout.addWidget(self.operation_progress_label)
        self.operation_progress = QProgressBar()
        self.operation_progress.setMinimum(0)
        self.operation_progress.setMaximum(100)
        layout.addWidget(self.operation_progress)
        
        # Overall progress bar
        self.overall_progress_label = QLabel("Overall Progress:")
        layout.addWidget(self.overall_progress_label)
        self.overall_progress = QProgressBar()
        self.overall_progress.setMinimum(0)
        layout.addWidget(self.overall_progress)
        
        # Status label
        self.status_label = QLabel("Status: Initializing...")
        layout.addWidget(self.status_label)
        
        # Cancel button
        self.cancel_button = QPushButton("Please wait...")
        # self.cancel_button.clicked.connect(self.reject)
        self.cancel_button.setEnabled(False)  # 一开始就禁用取消按钮
        layout.addWidget(self.cancel_button, alignment=Qt.AlignRight)
        
        self.setLayout(layout)
        self.canceled = False

    def closeEvent(self, event):
        # 如果不允许关闭，则忽略关闭事件
        if not self.can_close:
            event.ignore()
        else:
            super().closeEvent(event)
    
    # 添加一个方法，允许在批处理完成后关闭对话框
    def allow_close(self):
        self.can_close = True
        self.cancel_button.setText("Close")
        self.cancel_button.setEnabled(True)
        self.cancel_button.clicked.connect(self.accept)
        
    def set_tab_info(self, current, total):
        self.tab_label.setText(f"Processing tab: {current}/{total}")
    
    def set_max_operations(self, max_value):
        self.overall_progress.setMaximum(max_value)
    
    def update_operation_progress(self, value):
        self.operation_progress.setValue(value)
    
    def update_overall_progress(self, value):
        self.overall_progress.setValue(value)
    
    def update_operation(self, operation):
        self.operation_label.setText(f"Operation: {operation}")
        self.operation_progress.setValue(0)  # Reset operation progress
    
    def update_file(self, file_name):
        self.file_label.setText(f"File: {file_name}")
    
    def update_status(self, status):
        self.status_label.setText(f"Status: {status}")

#################################################################
# 推理设置对话栏
# InferenceSettingsDialog
#################################################################
class InferenceSettingsDialog(QtWidgets.QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Inference settings")
        app = QtWidgets.QApplication.instance()
        if app is not None:
            app.setStartDragTime(1)  # 1毫秒，几乎立即显示
        self.gpu_available = self.check_gpu_available()
        self.init_ui()
    # 在类中添加辅助方法，用于创建带有问号图标和工具提示的标签
    def create_label_with_tooltip(self, layout, text, tooltip):
        """创建带有问号图标和工具提示的标签布局"""
        container = QtWidgets.QHBoxLayout()
        label = QtWidgets.QLabel(text)

        # 创建问号图标标签
        help_icon = QtWidgets.QLabel("?")
        help_icon.setStyleSheet("""
            QLabel { 
                background-color: #337ab7; 
                color: white; 
                border-radius: 10px; 
                padding: 0 3px; 
                font-weight: bold;
            }
        """)

        # 格式化工具提示文本，使用HTML标签实现换行和样式
        formatted_tooltip = f"<div style='font-size:12pt; padding:5px;'>{tooltip.replace('. ', '.<br>')}</div>"
        help_icon.setToolTip(formatted_tooltip)

        # 设置工具提示样式表
        help_icon.setStyleSheet(help_icon.styleSheet() + """
            QToolTip {
                font-size: 12pt;
                background-color: #F5F5F5;
                color: #333333;
                border: 1px solid #CCCCCC;
                border-radius: 4px;
                padding: 5px;
                max-width: 400px;
            }
        """)

        help_icon.setFixedSize(20, 20)
        help_icon.setAlignment(Qt.AlignCenter)

        # 允许QLabel接收鼠标事件
        help_icon.setAttribute(QtCore.Qt.WA_Hover, True)
        help_icon.setMouseTracking(True)

        container.addWidget(label)
        container.addWidget(help_icon)
        container.addStretch()

        layout.addLayout(container)
        return label

    def check_gpu_available(self):
        """检查系统是否有可用的GPU"""
        try:
            import torch
            return torch.cuda.is_available()
        except ImportError:
            try:
                # 如果没有torch，尝试通过其他方式检测
                from ultralytics.utils.torch_utils import select_device
                device = select_device('0', verbose=False)
                return 'cpu' not in str(device)
            except:
                return False
    
    def set_settings(self, settings):
        self.conf_spinbox.setValue(settings.get("conf", 0.5))
        self.iou_spinbox.setValue(settings.get("iou", 0.7))
        
        # 设置设备选择，考虑GPU可用性
        device = settings.get("device", "GPU" if self.gpu_available else "CPU")
        if device == "GPU" and not self.gpu_available:
            device = "CPU"
        self.device_combobox.setCurrentText(device)

        # 设置图像大小和最大检测数量
        self.imgsz_spinbox.setValue(settings.get("imgsz", 1024))
        self.max_det_spinbox.setValue(settings.get("max_det", 500))
        
        self.save_path_edit.setText(settings.get("save_path", os.path.join(os.getcwd(), "Inference_OutPut")))
        
    def load_default_settings(self):
        self.conf_spinbox.setValue(0.5)
        self.iou_spinbox.setValue(0.7)
        self.device_combobox.setCurrentText("GPU" if self.gpu_available else "CPU")
        self.imgsz_spinbox.setValue(1024)  # 默认图像大小
        self.max_det_spinbox.setValue(500)  # 默认最大检测数量
        self.save_path_edit.setText(os.path.join(os.getcwd(), "Inference_OutPut"))

    def init_ui(self):
        layout = QtWidgets.QVBoxLayout()

        # 使用带问号图标的标签替换原始标签
        self.create_label_with_tooltip(
            layout, 
            "conf, the default value is 0.5.", 
            "Sets the minimum confidence threshold for detections. "
            "Objects detected with confidence below this threshold will be disregarded."
        )
        self.conf_spinbox = QtWidgets.QDoubleSpinBox()
        self.conf_spinbox.setRange(0.0, 1.0)
        self.conf_spinbox.setSingleStep(0.1)
        layout.addWidget(self.conf_spinbox)

        self.create_label_with_tooltip(
            layout, 
            "iou, the default value is 0.7", 
            "Intersection Over Union (IoU) threshold for Non-Maximum Suppression (NMS). "
            "Lower values result in fewer detections by eliminating overlapping boxes, useful for reducing duplicates."
        )
        self.iou_spinbox = QtWidgets.QDoubleSpinBox()
        self.iou_spinbox.setRange(0.0, 1.0)
        self.iou_spinbox.setSingleStep(0.1)
        layout.addWidget(self.iou_spinbox)
        
        # 新增控件：图像大小
        self.create_label_with_tooltip(
            layout, 
            "Image Size (imgsz), recommended to use 1024", 
            "If the inference speed is too slow, one can resort to 640 (at the expense of accuracy). "
            "Defines the image size for inference. Can be a single integer for square resizing or a (height, width) tuple."
        )
        self.imgsz_spinbox = QtWidgets.QSpinBox()
        self.imgsz_spinbox.setRange(320, 4096)  # 设置合理的范围
        self.imgsz_spinbox.setSingleStep(32)
        self.imgsz_spinbox.setValue(1024)  # 默认值
        layout.addWidget(self.imgsz_spinbox)
        
        # 新增控件：最大检测数量
        self.create_label_with_tooltip(
            layout, 
            "Maximum Detections (max_det), recommended to use 500", 
            "Maximum number of detections allowed per image."
            " Limits the total number of objects the model can detect in a single inference, preventing excessive outputs in dense scenes."
        )
        self.max_det_spinbox = QtWidgets.QSpinBox()
        self.max_det_spinbox.setRange(1, 5000)  # 设置合理的范围
        self.max_det_spinbox.setSingleStep(50)
        self.max_det_spinbox.setValue(500)  # 默认值
        layout.addWidget(self.max_det_spinbox)

        self.device_label = QtWidgets.QLabel("Inference device:")
        self.device_combobox = QtWidgets.QComboBox()
        self.device_combobox.addItem("CPU")
        if self.gpu_available:
            self.device_combobox.addItem("GPU")
        else:
            # 添加禁用的GPU选项
            self.device_combobox.addItem("GPU (Not applicable)")
            self.device_combobox.model().item(1).setEnabled(False)
        
        # 连接设备选择信号
        self.device_combobox.currentTextChanged.connect(self.on_device_changed)
        
        layout.addWidget(self.device_label)
        layout.addWidget(self.device_combobox)

        self.save_path_label = QtWidgets.QLabel("Save results file path:")
        self.save_path_edit = QtWidgets.QLineEdit()
        self.save_path_edit.setText(os.path.join(os.getcwd(), "Inference_OutPut"))  # 默认保存路径
        self.save_path_button = QtWidgets.QPushButton("Browse")
        self.save_path_button.clicked.connect(self.browse_save_path)
        save_path_layout = QtWidgets.QHBoxLayout()
        save_path_layout.addWidget(self.save_path_edit)
        save_path_layout.addWidget(self.save_path_button)
        layout.addWidget(self.save_path_label)
        layout.addLayout(save_path_layout)

        self.button_box = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel)
        self.button_box.accepted.connect(self.accept)
        self.button_box.rejected.connect(self.reject)
        layout.addWidget(self.button_box)

        self.setLayout(layout)
        
    def on_device_changed(self, device_text):
        """当设备选择改变时调用"""
        if device_text == "GPU" and not self.gpu_available:
            QMessageBox.warning(self, "GPU不可用", 
                                "未检测到可用的GPU或CUDA环境。将使用CPU进行推理。")
            self.device_combobox.setCurrentText("CPU")

    def browse_save_path(self):
        options = QtWidgets.QFileDialog.Options()
        save_path = QtWidgets.QFileDialog.getExistingDirectory(self, "Select Save Directory", options=options)
        if save_path:
            self.save_path_edit.setText(save_path)

    def get_settings(self):
        return {
            "conf": self.conf_spinbox.value(),
            "iou": self.iou_spinbox.value(),
            "device": self.device_combobox.currentText(),
            "imgsz": self.imgsz_spinbox.value(),  # 新增参数
            "max_det": self.max_det_spinbox.value(),  # 新增参数
            "save_path": self.save_path_edit.text()
        }

    def save_settings(self):
        settings = QtCore.QSettings("MyCompany", "MyApp")
        settings.setValue("conf", self.conf_spinbox.value())
        settings.setValue("iou", self.iou_spinbox.value())
        settings.setValue("device", self.device_combobox.currentText())
        settings.setValue("imgsz", self.imgsz_spinbox.value())  # 新增参数
        settings.setValue("max_det", self.max_det_spinbox.value())  # 新增参数
        settings.setValue("save_path", self.save_path_edit.text())

    def accept(self):
        # 再次验证设备选择
        if self.device_combobox.currentText() == "GPU" and not self.gpu_available:
            QMessageBox.warning(self, "GPU不可用", 
                                "未检测到可用的GPU或CUDA环境。将使用CPU进行推理。")
            self.device_combobox.setCurrentText("CPU")
            return
        
        self.save_settings()
        super().accept()

#################################################################
# 比例尺设置对话栏
# SetMeasuringScaleDialog
#################################################################

class SetMeasuringScaleDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent = parent
        self.setWindowTitle("Set the measurement scale")

        # 创建控件
        self.pixel_distance_label = QLabel("Pixels Distance:")
        self.pixel_distance_edit = QLineEdit()

        self.real_distance_label = QLabel("Known Real Distance:")
        self.real_distance_edit = QLineEdit()

        self.unit_label = QLabel("Unit of Length:")
        self.unit_combo = QComboBox()
        self.unit_combo.addItems(["nm","μm", "mm", "cm", "m", "km"])  # 根据需要添加单位

        self.global_checkbox = QCheckBox("Global?(Applicable to all images)")

        self.ok_button = QPushButton("OK")
        self.cancel_button = QPushButton("Cancel")

        # 布局
        layout = QVBoxLayout()
        layout.addWidget(self.pixel_distance_label)
        layout.addWidget(self.pixel_distance_edit)
        layout.addWidget(self.real_distance_label)
        layout.addWidget(self.real_distance_edit)
        layout.addWidget(self.unit_label)
        layout.addWidget(self.unit_combo)
        layout.addWidget(self.global_checkbox)

        button_layout = QHBoxLayout()
        button_layout.addWidget(self.ok_button)
        button_layout.addWidget(self.cancel_button)
        layout.addLayout(button_layout)

        self.setLayout(layout)

        # 连接信号
        self.ok_button.clicked.connect(self.accept)
        self.cancel_button.clicked.connect(self.reject)
        
        # 加载已有比例尺信息（如果有）
        self.load_existing_scale_info()
    
    def load_existing_scale_info(self):
        """加载现有的比例尺信息作为默认值"""
        scale_info = None
        
        # 首先尝试获取全局比例尺信息
        if self.parent and hasattr(self.parent, 'global_scale_info') and self.parent.global_scale_info:
            scale_info = self.parent.global_scale_info
            # 如果是全局比例尺，默认勾选全局复选框
            self.global_checkbox.setChecked(True)
        # 如果没有全局比例尺，尝试获取当前视图的比例尺
        elif self.parent and hasattr(self.parent, 'get_current_graphics_view'):
            current_view = self.parent.get_current_graphics_view()
            if current_view and hasattr(current_view, 'scale_info') and current_view.scale_info:
                scale_info = current_view.scale_info
                # 如果是局部比例尺，不勾选全局复选框
                self.global_checkbox.setChecked(False)
        
        # 如果找到比例尺信息，填充到对话框中
        if scale_info:
            # 假设scale_info中有scale和unit字段
            scale = scale_info.get('scale', 1.0)
            unit = scale_info.get('unit', 'μm')
            
            # 假设是1:1的比例，即像素距离为1，实际距离为scale
            self.pixel_distance_edit.setText("1")
            self.real_distance_edit.setText(str(scale))
            
            # 设置单位下拉框
            index = self.unit_combo.findText(unit)
            if index >= 0:
                self.unit_combo.setCurrentIndex(index)

    def get_scale_info(self):
        pixel_distance = float(self.pixel_distance_edit.text()) if self.pixel_distance_edit.text() else 0
        real_distance = float(self.real_distance_edit.text()) if self.real_distance_edit.text() else 0
        unit = self.unit_combo.currentText()
        is_global = self.global_checkbox.isChecked()
        return pixel_distance, real_distance, unit, is_global
    
#################################################################
# 在每次创建完形状后弹出的对话栏，选择类别
# LabelInputDialog
#################################################################

class LabelInputDialog(QDialog):
    def __init__(self, existing_labels, parent=None):
        super(LabelInputDialog, self).__init__(parent)
        self.setWindowTitle('Label Input Dialog')
        self.selected_label = None
        self.apply_to_shape_type = False
        self.apply_to_all_shapes = False

        layout = QVBoxLayout()

        label_label = QLabel('Please enter a label name:')
        layout.addWidget(label_label)

        self.label_combobox = QComboBox()
        self.label_combobox.setEditable(True)
        self.label_combobox.addItems(existing_labels)
        layout.addWidget(self.label_combobox)

        self.checkbox_shape_type = QCheckBox('Applies to all current shape types')
        layout.addWidget(self.checkbox_shape_type)

        self.checkbox_all_shapes = QCheckBox('Apply to all shapes')
        layout.addWidget(self.checkbox_all_shapes)

        button_layout = QHBoxLayout()
        self.ok_button = QPushButton('OK')
        self.cancel_button = QPushButton('Cancel')
        button_layout.addWidget(self.ok_button)
        button_layout.addWidget(self.cancel_button)
        layout.addLayout(button_layout)

        self.setLayout(layout)

        self.ok_button.clicked.connect(self.accept)
        self.cancel_button.clicked.connect(self.reject)

        self.checkbox_all_shapes.stateChanged.connect(self.on_all_shapes_checked)

    def on_all_shapes_checked(self, state):
        if state == Qt.Checked:
            self.checkbox_shape_type.setChecked(False)
            self.checkbox_shape_type.setEnabled(False)
        else:
            self.checkbox_shape_type.setEnabled(True)

    def get_label(self):
        text = self.label_combobox.currentText()
        if text == '':
            return None
        else:
            return text.strip()

    def accept(self):
        self.selected_label = self.get_label()
        self.apply_to_shape_type = self.checkbox_shape_type.isChecked()
        self.apply_to_all_shapes = self.checkbox_all_shapes.isChecked()
        super(LabelInputDialog, self).accept()

#################################################################
# 进行推理进程中的进度条，分别在InferenceThread中三个线程启动被调用
# ShuttleProgressBar is called in ProgressDialog class
# It is called when three threads are initiated in the InferenceThread
#################################################################

class ShuttleProgressBar(QProgressBar):
    """自定义的摆渡式进度条，显示一个固定宽度的滑块"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setTextVisible(False)
        self.setRange(0, 100)
        self.setValue(0)
        
        # 滑块位置和宽度
        self._chunk_position = 0
        self._chunk_width = 40  # 滑块宽度，单位是像素
        
        # 设置基本样式
        self.setStyleSheet("""
            QProgressBar {
                border: 1px solid #CCCCCC;
                border-radius: 3px;
                background-color: #F0F0F0;
            }
        """)
    
    def setChunkPosition(self, position):
        """设置滑块位置"""
        self._chunk_position = position
        self.update()  # 触发重绘
    
    def chunkPosition(self):
        """获取滑块位置"""
        return self._chunk_position
    
    # 定义属性以便用于动画 - 使用pyqtProperty而不是Property
    chunk_position = pyqtProperty(int, chunkPosition, setChunkPosition)
    
    def paintEvent(self, event):
        """自定义绘制进度条"""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        
        # 绘制背景
        painter.fillRect(self.rect(), QColor("#F0F0F0"))
        
        # 计算滑块位置
        bar_width = self.width() - 2  # 减去边框宽度
        max_position = bar_width - self._chunk_width
        
        # 确保滑块位置在有效范围内
        actual_position = min(max(0, int(self._chunk_position * max_position / 100)), max_position)
        
        # 绘制滑块
        chunk_rect = QRect(actual_position + 1, 1, self._chunk_width, self.height() - 2)
        painter.fillRect(chunk_rect, QColor("#4CAF50"))
        
        painter.end()

class ProgressDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Processing")
        self.setModal(True)
        self.setMinimumWidth(400)
        self.setMinimumHeight(120)
        
        # 创建布局和组件
        self.layout = QVBoxLayout(self)
        self.label = QLabel("Processing...", self)
        self.label.setAlignment(Qt.AlignCenter)
        
        # 使用自定义进度条
        self.progress_bar = ShuttleProgressBar(self)
        self.progress_bar.setFixedHeight(24)
        
        self.layout.addWidget(self.label)
        self.layout.addWidget(self.progress_bar)
        
        # 创建动画
        self.animation = QPropertyAnimation(self.progress_bar, b"chunk_position")
        self.animation.setDuration(1500)  # 1.5秒完成一次移动
        self.animation.setStartValue(0)
        self.animation.setEndValue(100)
        self.animation.setEasingCurve(QEasingCurve.InOutSine)  # 使用平滑的缓动曲线
        
        # 设置动画循环
        self.animation.finished.connect(self.reverse_animation)

    def showEvent(self, event):
        """对话框显示时启动动画"""
        super().showEvent(event)
        self.animation.start()
    
    def reverse_animation(self):
        """反转动画方向"""
        # 交换起始值和结束值
        start_value = self.animation.startValue()
        end_value = self.animation.endValue()
        self.animation.setStartValue(end_value)
        self.animation.setEndValue(start_value)
        self.animation.start()
    
    def process_events(self):
        """处理挂起的事件以确保UI更新"""
        QEventLoop().processEvents(QEventLoop.AllEvents, 10)

    def update_message(self, message):
        """更新显示的消息文本"""
        self.label.setText(message)
        self.label.repaint()
    
    def closeEvent(self, event):
        """关闭窗口时停止动画"""
        self.animation.stop()
        super().closeEvent(event)
    
    def accept(self):
        """接受对话框时停止动画"""
        self.animation.stop()
        super().accept()
    
    def reject(self):
        """拒绝对话框时停止动画"""
        self.animation.stop()
        super().reject()

##########################################################################
# 颜色设置对话栏
# ColorSettingsDialog
##########################################################################

class ColorSettingsDialog(QtWidgets.QDialog):
    def __init__(self, parent=None, color_map=None):
        super().__init__(parent)
        self.setWindowTitle("Color Settings")
        self.color_map = color_map or {}
        self.init_ui()
        
    def init_ui(self):
        layout = QtWidgets.QVBoxLayout()
        
        # 创建颜色映射表格
        self.table = QtWidgets.QTableWidget()
        self.table.setColumnCount(2)
        self.table.setHorizontalHeaderLabels(["Classnum", "Color"])
        self.table.horizontalHeader().setSectionResizeMode(1, QtWidgets.QHeaderView.Stretch)
        self.populate_table()
        layout.addWidget(self.table)
        
        # 添加按钮
        button_layout = QtWidgets.QHBoxLayout()
        self.add_button = QtWidgets.QPushButton("Add Category")
        self.add_button.clicked.connect(self.add_class)
        
        self.button_box = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel)
        self.button_box.accepted.connect(self.accept)
        self.button_box.rejected.connect(self.reject)
        
        button_layout.addWidget(self.add_button)
        button_layout.addStretch()
        button_layout.addWidget(self.button_box)
        
        layout.addLayout(button_layout)
        self.setLayout(layout)
        self.resize(300, 400)
        
    def populate_table(self):
        # 清空表格
        self.table.setRowCount(0)
        
        # 添加已有的颜色映射
        for class_num, color in sorted(self.color_map.items()):
            self.add_row(class_num, color)
            
    def add_row(self, class_num, color):
        row = self.table.rowCount()
        self.table.insertRow(row)
        
        # 创建类别编号项
        class_item = QtWidgets.QTableWidgetItem(str(class_num))
        class_item.setData(Qt.UserRole, class_num)
        self.table.setItem(row, 0, class_item)
        
        # 创建颜色项
        color_item = QtWidgets.QTableWidgetItem()
        color_item.setBackground(color)
        color_item.setText(f"RGB: {color.red()}, {color.green()}, {color.blue()}")
        self.table.setItem(row, 1, color_item)
        
    def change_color(self, row, col):
        if col != 1:  # 只处理颜色列
            return
            
        current_color = self.table.item(row, 1).background().color()
        new_color = QtWidgets.QColorDialog.getColor(current_color, self)
        
        if new_color.isValid():
            self.table.item(row, 1).setBackground(new_color)
            self.table.item(row, 1).setText(f"RGB: {new_color.red()}, {new_color.green()}, {new_color.blue()}")
            
    def add_class(self):
        # 获取当前最大的类别编号
        max_class = -1
        for i in range(self.table.rowCount()):
            class_num = int(self.table.item(i, 0).text())
            max_class = max(max_class, class_num)
            
        # 添加新类别
        self.add_row(max_class + 1, QtGui.QColor(0, 0, 0))
        
    def get_color_map(self):
        color_map = {}
        for i in range(self.table.rowCount()):
            class_num = int(self.table.item(i, 0).text())
            color = self.table.item(i, 1).background().color()
            color_map[class_num] = color
        return color_map
        
    def showEvent(self, event):
        super().showEvent(event)
        # 连接信号槽，避免在构造函数中连接导致的重复触发
        self.table.cellDoubleClicked.connect(self.change_color)


##########################################################################
# 热图生成对话栏
# HeatMapDialog
##########################################################################

class HeatMapDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent = parent  # 保存父窗口引用
        
        # 添加调试信息
        print(f"HeatMapDialog parent: {type(parent).__name__}")
        
        # 初始化main_window变量
        self.main_window = None
        
        # 查找并保存对主窗口的引用 - 更安全的实现
        temp_parent = parent
        while temp_parent is not None:
            # 如果找到带有tabWidget属性的对象，认为它是主窗口
            if hasattr(temp_parent, 'tabWidget'):
                self.main_window = temp_parent
                break
            
            # 尝试获取父对象 - 同时处理属性和方法两种情况
            if hasattr(temp_parent, 'parent'):
                parent_attr = getattr(temp_parent, 'parent')
                if callable(parent_attr):
                    try:
                        temp_parent = parent_attr()
                    except:
                        temp_parent = None
                else:
                    temp_parent = parent_attr
            else:
                temp_parent = None
        
        print(f"Found main window: {self.main_window is not None}")
        
        # 初始化变量
        self.scale_info = None
        # 存储临时文件路径便于清理
        self.temp_file = None
        self.setWindowTitle("Heat map generator")
        self.setMinimumWidth(500)
        
        # 创建布局
        self.layout = QVBoxLayout()
        
        # 特征选择
        feature_layout = QHBoxLayout()
        feature_label = QLabel("Select Features:")
        self.feature_combo = QComboBox()
        self.features = [
            "Area", "Perimeter", "MER Length", "MER Width", 
            "Circularity", "Eccentricity", "ACH", "PCH", 
            "Roundness", "Convexity", "Solidity"
        ]
        self.feature_combo.addItems(self.features)
        feature_layout.addWidget(feature_label)
        feature_layout.addWidget(self.feature_combo)
        self.layout.addLayout(feature_layout)
        
        # 比例尺信息容器（初始隐藏）
        self.scale_info_container = QWidget()
        scale_layout = QVBoxLayout(self.scale_info_container)
        
        # 添加比例尺标签
        self.scale_info_label = QLabel("Scale Information:")
        scale_layout.addWidget(self.scale_info_label)
        
        # 比例尺信息显示
        # scale_details_layout = QHBoxLayout()
        # 比例尺信息显示 - 移除设置按钮
        self.scale_value_label = QLabel("Scale not set (using pixel units)")
        scale_layout.addWidget(self.scale_value_label)
        # self.set_scale_button = QPushButton("Set Scale")
        # 比例尺警告标签
        self.scale_warning_label = QLabel("Note: The selected feature requires scale information for accurate visualization.")
        self.scale_warning_label.setStyleSheet("color: #FF6347;")  # 使用红色文字突出显示
        scale_layout.addWidget(self.scale_warning_label)
        
        self.layout.addWidget(self.scale_info_container)
        self.scale_info_container.hide()  # 初始隐藏
        
        
        # 颜色方案选择
        colormap_layout = QHBoxLayout()
        colormap_label = QLabel("Choosing color schemes:")
        self.colormap_combo = QComboBox()
        self.colormaps = [
            "viridis", "plasma", "inferno", "magma", "cividis",
            "Spectral", "coolwarm", "YlOrRd", "YlGnBu", "RdYlBu"
        ]
        self.colormap_combo.addItems(self.colormaps)
        colormap_layout.addWidget(colormap_label)
        colormap_layout.addWidget(self.colormap_combo)
        self.layout.addLayout(colormap_layout)
        
        # 颜色预览
        self.preview_label = QLabel("Color Preview:")
        self.layout.addWidget(self.preview_label)
        
        self.colormap_preview = QLabel()
        self.colormap_preview.setMinimumHeight(30)
        self.colormap_preview.setMaximumHeight(30)
        self.layout.addWidget(self.colormap_preview)
        
        # 导出选项
        export_layout = QHBoxLayout()
        self.export_path_edit = QtWidgets.QLineEdit()
        self.export_path_edit.setReadOnly(True)
        self.export_path_edit.setPlaceholderText("Select save path...")
        self.browse_button = QPushButton("browse...")
        self.browse_button.clicked.connect(self.browse_output_folder)
        export_layout.addWidget(self.export_path_edit)
        export_layout.addWidget(self.browse_button)
        self.layout.addLayout(export_layout)
        
        # 按钮
        button_layout = QHBoxLayout()
        self.generate_button = QPushButton("Generating heat map")
        self.generate_button.clicked.connect(self.accept)
        self.cancel_button = QPushButton("cancel")
        self.cancel_button.clicked.connect(self.reject)
        button_layout.addWidget(self.generate_button)
        button_layout.addWidget(self.cancel_button)
        self.layout.addLayout(button_layout)
        
        self.setLayout(self.layout)
        
        # 连接信号
        self.colormap_combo.currentIndexChanged.connect(self.update_colormap_preview)
        self.feature_combo.currentIndexChanged.connect(self.check_scale_needed)
        
 
        # 初始化颜色预览
        self.update_colormap_preview()
        

        
        # 检查当前选择的特征是否需要比例尺
        self.check_scale_needed()
        
        # 加载当前比例尺信息（如果有）
        self.load_scale_info()
    
# 在 HeatMapDialog 的 load_scale_info 方法中

    def load_scale_info(self):
        """加载当前比例尺信息"""
        # 尝试找到主窗口对象
        main_window = self.parent
        while main_window and not hasattr(main_window, 'tabWidget'):
            if hasattr(main_window, 'parent'):
                # 修复: 安全地获取父对象，同时处理属性和方法两种情况
                parent_attr = getattr(main_window, 'parent')
                if callable(parent_attr):
                    try:
                        main_window = parent_attr()
                    except:
                        main_window = None
                else:
                    main_window = parent_attr
            else:
                main_window = None
        
        # 首先尝试获取全局比例尺信息（从主窗口或当前父对象）
        if main_window and hasattr(main_window, 'global_scale_info') and main_window.global_scale_info:
            self.scale_info = main_window.global_scale_info
            self.update_scale_info_display()
        elif self.parent and hasattr(self.parent, 'global_scale_info') and self.parent.global_scale_info:
            self.scale_info = self.parent.global_scale_info
            self.update_scale_info_display()
        else:
            # 如果没有全局比例尺，尝试获取当前视图的比例尺信息
            if main_window and hasattr(main_window, 'get_current_graphics_view'):
                current_view = main_window.get_current_graphics_view()
                if current_view and hasattr(current_view, 'scale_info') and current_view.scale_info:
                    self.scale_info = current_view.scale_info
                    self.update_scale_info_display()
    
    def check_scale_needed(self):
        """检查所选特征是否需要比例尺信息"""
        current_feature = self.feature_combo.currentText()
        scale_needed_features = ["Area", "Perimeter", "MER Length", "MER Width"]
        
        if current_feature in scale_needed_features:
            self.scale_info_container.show()
            self.adjustSize()  # 调整对话框大小以适应新显示的内容
        else:
            self.scale_info_container.hide()
            self.adjustSize()  # 调整对话框大小
    
    def update_scale_info_display(self):
        """更新比例尺信息显示"""
        if self.scale_info:
            scale = self.scale_info.get('scale', 1.0)
            unit = self.scale_info.get('unit', 'pixel')
            is_global = self.scale_info.get('is_global', False)
            
            # 区分全局比例尺和局部比例尺
            if is_global:
                self.scale_value_label.setText(f"Using global scale: 1 pixel = {scale} {unit}")
                self.scale_value_label.setStyleSheet("color: green;")
            else:
                self.scale_value_label.setText(f"Using image scale: 1 pixel = {scale} {unit}")
                self.scale_value_label.setStyleSheet("color: blue;")
        else:
            self.scale_value_label.setText("No scale information available (using pixel units)")
            self.scale_value_label.setStyleSheet("color: red;")
            
            # 如果特征需要比例尺但没有设置，显示更明显的警告
            current_feature = self.feature_combo.currentText()
            scale_needed_features = ["Area", "Perimeter", "MER Length", "MER Width"]
            if current_feature in scale_needed_features:
                self.scale_warning_label.setText("Warning: The selected feature requires scale information for meaningful results!")
                self.scale_warning_label.setStyleSheet("color: red; font-weight: bold;")
            else:
                self.scale_warning_label.setText("Note: The selected feature requires scale information for accurate visualization.")
                self.scale_warning_label.setStyleSheet("color: #FF6347;")
    
    def update_colormap_preview(self):
        """更新颜色方案预览"""
        try:
            import matplotlib.pyplot as plt
            
            colormap_name = self.colormap_combo.currentText()
            
            # 清理之前的临时文件
            if self.temp_file and os.path.exists(self.temp_file):
                try:
                    os.remove(self.temp_file)
                except:
                    pass
            
            # 创建一个新的临时文件
            fd, self.temp_file = tempfile.mkstemp(suffix='.png')
            os.close(fd)
            
            # 创建一个渐变色的预览图
            gradient = np.linspace(0, 1, 400)
            gradient = np.vstack((gradient, gradient))
            
            # 确保先关闭之前的图形
            plt.close('all')
            
            # 创建颜色图预览
            fig = plt.figure(figsize=(4, 0.3))
            plt.imshow(gradient, aspect='auto', cmap=colormap_name)
            plt.axis('off')
            
            # 保存为临时文件
            fig.savefig(self.temp_file, bbox_inches='tight', pad_inches=0, dpi=100)
            plt.close(fig)  # 确保关闭图形
            
            # 加载并显示预览
            pixmap = QPixmap(self.temp_file)
            self.colormap_preview.setPixmap(pixmap)
            
        except Exception as e:
            print(f"Failed to update color preview: {str(e)}")
    
    def browse_output_folder(self):
        """打开文件对话框选择导出路径"""
        folder_path = QFileDialog.getExistingDirectory(self, "Select save path")
        if folder_path:
            self.export_path_edit.setText(folder_path)
    
    def get_settings(self):
        """返回用户选择的设置"""
        settings = {
            "feature": self.feature_combo.currentText(),
            "colormap": self.colormap_combo.currentText(),
            "output_path": self.export_path_edit.text(),
            "scale_info": self.scale_info  # 添加比例尺信息
        }
        return settings  # 添加这一行，返回设置
        
    def closeEvent(self, event):
        # 确保清理临时文件
        if self.temp_file and os.path.exists(self.temp_file):
            try:
                os.remove(self.temp_file)
            except:
                pass
        super().closeEvent(event)