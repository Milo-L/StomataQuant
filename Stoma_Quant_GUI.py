from PyQt5 import QtCore, QtWidgets, QtGui
from PyQt5.QtWidgets import QMainWindow, QAction, QToolButton, QMenu, QLabel, QSlider, QDockWidget, QActionGroup
from PyQt5.QtCore import QCoreApplication
import PyQt5
import os
plugin_path = os.path.join(os.path.dirname(PyQt5.__file__), 'Qt', 'plugins')
print(f"plugin_path: {plugin_path}")
QCoreApplication.addLibraryPath(plugin_path)
    # 导入 ShapeListDock 和 LabelListDock


class MainWindow(QMainWindow):
    def setupUi(self, MainWindow):
        MainWindow.setObjectName("MainWindow")
        MainWindow.resize(1200, 800)

        # 设置窗口图标
        MainWindow.setWindowIcon(QtGui.QIcon(r"ICON.png"))

        # 主窗口和中央控件
        self.centralwidget = QtWidgets.QWidget(MainWindow)
        self.centralwidget.setObjectName("centralwidget")

        # 中央部件布局
        self.centralLayout = QtWidgets.QVBoxLayout(self.centralwidget)
        self.centralLayout.setObjectName("centralLayout")

        # 多文档界面 (QTabWidget)
        self.tabWidget = QtWidgets.QTabWidget(self.centralwidget)
        self.tabWidget.setObjectName("tabWidget")
        self.tabWidget.setTabsClosable(True)
        self.tabWidget.setUsesScrollButtons(True)
        self.tabWidget.setMovable(True)
        self.centralLayout.addWidget(self.tabWidget)
        self.setTabShape(QtWidgets.QTabWidget.Triangular)
        self.setCentralWidget(self.centralwidget)

        # 菜单栏
        self.menubar = QtWidgets.QMenuBar(MainWindow)
        self.menubar.setGeometry(QtCore.QRect(0, 0, 1200, 21))
        self.menubar.setObjectName("menubar")

        # 菜单项
        # 创建保存注释和导入注释的子菜单
        self.menuSaveAnnotation = QtWidgets.QMenu("Save Annotation", MainWindow)
        self.menuSaveAnnotation.setObjectName("menuSaveAnnotation")
        self.menuImportAnnotation = QtWidgets.QMenu("Import Annotation", MainWindow)
        self.menuImportAnnotation.setObjectName("menuImportAnnotation")


        self.menuFile = QtWidgets.QMenu(self.menubar)
        self.menuFile.setObjectName("menuFile")
        self.menuView = QtWidgets.QMenu(self.menubar)
        self.menuView.setObjectName("menuView")
        # self.menuImage = QtWidgets.QMenu(self.menubar)
        # self.menuImage.setObjectName("menuImage")
        self.menuAnalyze = QtWidgets.QMenu(self.menubar)
        self.menuAnalyze.setObjectName("menuAnalyze")
        self.menuSetting = QtWidgets.QMenu(self.menubar)  # 初始化 menuSetting
        self.menuSetting.setObjectName("menuSetting")
        
                # 创建More Information菜单
        self.menuMoreInfo = QtWidgets.QMenu(self.menubar)
        self.menuMoreInfo.setObjectName("menuMoreInfo")

        # 设置菜单栏
        MainWindow.setMenuBar(self.menubar)

        # 工具栏
        self.toolBar = QtWidgets.QToolBar(MainWindow)
        self.toolBar.setObjectName("toolBar")

     # 确保工具栏在菜单栏下方
        MainWindow.addToolBar(QtCore.Qt.TopToolBarArea, self.toolBar)

        # 状态栏
        self.statusbar = QtWidgets.QStatusBar(MainWindow)
        self.statusbar.setObjectName("statusbar")
        MainWindow.setStatusBar(self.statusbar)



        # 添加菜单栏的动作
        self.actionOpen = QtWidgets.QAction(MainWindow)
        self.actionOpen.setObjectName("actionOpen")
        self.actionSavePolygonAnnotataion = QtWidgets.QAction(MainWindow)
        self.actionSavePolygonAnnotataion.setObjectName("actionSavePolygonAnnotataion")
        self.actionSaveRectangleAnnotataion = QtWidgets.QAction(MainWindow)
        self.actionSaveRectangleAnnotataion.setObjectName("actionSaveRectangleAnnotataion")
        self.actionSaveRotatedRectangleAnnotataion = QtWidgets.QAction(MainWindow)
        self.actionSaveRotatedRectangleAnnotataion.setObjectName("actionSaveRotatedRectangleAnnotataion")
        self.actionImportPolygonAnnotataion = QtWidgets.QAction(MainWindow)
        self.actionImportPolygonAnnotataion.setObjectName("actionImportPolygonAnnotataion")
        self.actionImportRectangleAnnotataion = QtWidgets.QAction(MainWindow)
        self.actionImportRectangleAnnotataion.setObjectName("actionImportRectangleAnnotataion")
        self.actionImportRotatedRectangleAnnotataion = QtWidgets.QAction(MainWindow)
        self.actionImportRotatedRectangleAnnotataion.setObjectName("actionImportRotatedRectangleAnnotataion")
        self.actionClose = QtWidgets.QAction(MainWindow)
        self.actionClose.setObjectName("actionClose")
        self.actionShowPoint = QtWidgets.QAction(MainWindow)
        self.actionShowPoint.setObjectName("ShowPoint")
        self.actionShowID = QtWidgets.QAction(MainWindow)
        self.actionShowID.setObjectName("ShowEdge")
        self.actionColorSettings = QtWidgets.QAction(MainWindow)
        self.actionColorSettings.setObjectName("ColorSettings")
        self.actionHeatMap = QtWidgets.QAction(MainWindow)
        self.actionHeatMap.setObjectName("HeatMap")
        # self.actionUndo = QtWidgets.QAction(MainWindow)
        # self.actionUndo.setObjectName("actionUndo")
        # self.actionRedo = QtWidgets.QAction(MainWindow)
        # self.actionRedo.setObjectName("actionRedo")
        # self.actionAdjust = QtWidgets.QAction(MainWindow)
        # self.actionAdjust.setObjectName("actionAdjust")
        # self.actionProcess = QtWidgets.QAction(MainWindow)
        # self.actionProcess.setObjectName("actionProcess")
        # 在创建其他动作的区域添加此代码
        self.actionShortcutHelp = QtWidgets.QAction(MainWindow)
        self.actionShortcutHelp.setObjectName("actionShortcutHelp")

        self.actionABorAD = QtWidgets.QAction(MainWindow)
        self.actionABorAD.setObjectName("actionABorAD")

        self.actionSetMeasuringScale = QtWidgets.QAction(MainWindow)
        self.actionSetMeasuringScale.setObjectName("actionSetMeasuringScale")

        self.actionShapeFilter = QtWidgets.QAction(MainWindow)
        # self.actionShapeFilter.setObjectName("actionShapeFilter")

        self.actionModelSetting = QtWidgets.QAction(MainWindow)
        self.actionModelSetting.setObjectName("actionModelSetting")
        self.actionInferenceSetting = QtWidgets.QAction(MainWindow)
        self.actionInferenceSetting.setObjectName("actionInferenceSetting")
        
        # 添加Batch Processing动作
        self.actionBatchProcessing = QtWidgets.QAction(MainWindow)
        self.actionBatchProcessing.setObjectName("actionBatchProcessing")

                # 创建Batch Export子菜单
        self.menuBatchExport = QtWidgets.QMenu("Batch Export", MainWindow)
        self.menuBatchExport.setObjectName("menuBatchExport")

        # 创建三个批量导出动作
        self.actionBatchExportPolygon = QtWidgets.QAction(MainWindow)
        self.actionBatchExportPolygon.setObjectName("actionBatchExportPolygon")
        self.actionBatchExportRectangle = QtWidgets.QAction(MainWindow)
        self.actionBatchExportRectangle.setObjectName("actionBatchExportRectangle")
        self.actionBatchExportRotatedRectangle = QtWidgets.QAction(MainWindow)
        self.actionBatchExportRotatedRectangle.setObjectName("actionBatchExportRotatedRectangle")
        # self.actionBatchExport = QtWidgets.QAction(MainWindow)
        # self.actionBatchExport.setObjectName("actionBatchExport")

        self.menuBatchImport = QtWidgets.QMenu("Batch Import", MainWindow)
        self.menuBatchImport.setObjectName("menuBatchImport")
        # 创建三个批量导出动作
        self.actionBatchImportPolygon = QtWidgets.QAction(MainWindow)
        self.actionBatchImportPolygon.setObjectName("actionBatchImportPolygon")
        self.actionBatchImportRectangle = QtWidgets.QAction(MainWindow)
        self.actionBatchImportRectangle.setObjectName("actionBatchImportRectangle")
        self.actionBatchImportRotatedRectangle = QtWidgets.QAction(MainWindow)
        self.actionBatchImportRotatedRectangle.setObjectName("actionBatchImportRotatedRectangle")

        # 将动作添加到菜单项
        self.menuFile.addAction(self.actionOpen)

        # 添加保存注释子菜单及其动作
        self.menuSaveAnnotation.addAction(self.actionSavePolygonAnnotataion)
        self.menuSaveAnnotation.addAction(self.actionSaveRectangleAnnotataion)
        self.menuSaveAnnotation.addAction(self.actionSaveRotatedRectangleAnnotataion)
        self.menuFile.addMenu(self.menuSaveAnnotation)

        # 添加导入注释子菜单及其动作
        self.menuImportAnnotation.addAction(self.actionImportPolygonAnnotataion)
        self.menuImportAnnotation.addAction(self.actionImportRectangleAnnotataion)
        self.menuImportAnnotation.addAction(self.actionImportRotatedRectangleAnnotataion)
        self.menuFile.addMenu(self.menuImportAnnotation)

        # self.menuFile.addAction(self.actionShowPoint)
        self.menuFile.addSeparator()
        self.menuFile.addAction(self.actionClose)

        self.menuView.addAction(self.actionShowPoint)
        self.menuView.addAction(self.actionShowID)
        self.menuView.addAction(self.actionColorSettings)
        self.menuView.addAction(self.actionHeatMap)


        # self.menuImage.addAction(self.actionAdjust)
        # self.menuImage.addAction(self.actionProcess)

        self.menuAnalyze.addAction(self.actionABorAD)
        # self.menuAnalyze.addAction(self.actionShapeFilter)
        self.menuAnalyze.addAction(self.actionSetMeasuringScale)

                # 创建子菜单动作
        self.actionFilterAllEdges = QtWidgets.QAction("Filter Out All Edges", MainWindow)
        self.actionFilterTopLeft = QtWidgets.QAction("Filter Out Top and Left Edges", MainWindow)
        self.actionFilterRightBottom = QtWidgets.QAction("Filter Out Right and Bottom Edges", MainWindow)
                # 初始化这三个动作为不可用
        self.actionFilterAllEdges.setEnabled(False)
        self.actionFilterTopLeft.setEnabled(False)
        self.actionFilterRightBottom.setEnabled(False)


        # 创建 Shape Filter 菜单并添加子动作
        self.menuShapeFilter = QtWidgets.QMenu("Shape Filter", MainWindow)
        self.menuShapeFilter.addAction(self.actionFilterAllEdges)
        self.menuShapeFilter.addAction(self.actionFilterTopLeft)
        self.menuShapeFilter.addAction(self.actionFilterRightBottom)

        # 将 Shape Filter 菜单添加到 menuAnalyze
        self.menuAnalyze.addMenu(self.menuShapeFilter)

        self.menuMoreInfo.addAction(self.actionBatchProcessing)
        # 替换现有的添加动作代码
        # self.menuMoreInfo.addAction(self.actionBatchExport)

        # 向Batch Export子菜单添加三个动作
        self.menuBatchExport.addAction(self.actionBatchExportPolygon)
        self.menuBatchExport.addAction(self.actionBatchExportRectangle)
        self.menuBatchExport.addAction(self.actionBatchExportRotatedRectangle)
        # 将子菜单添加到More菜单
        self.menuMoreInfo.addMenu(self.menuBatchExport)

        # 向Batch Export子菜单添加三个动作
        self.menuBatchImport.addAction(self.actionBatchImportPolygon)
        self.menuBatchImport.addAction(self.actionBatchImportRectangle)
        self.menuBatchImport.addAction(self.actionBatchImportRotatedRectangle)

        self.menuMoreInfo.addMenu(self.menuBatchImport)

        self.menuSetting.addAction(self.actionModelSetting)  # 添加动作到 menuSetting
        self.menuSetting.addAction(self.actionInferenceSetting)  # 添加动作到 menuSetting
                # 在将其他动作添加到More菜单后添加这一行
        self.menuMoreInfo.addSeparator()  # 添加分隔线
        self.menuMoreInfo.addAction(self.actionShortcutHelp)
        # 将菜单添加到菜单栏
        self.menubar.addAction(self.menuFile.menuAction())
        self.menubar.addAction(self.menuView.menuAction())
        # self.menubar.addAction(self.menuImage.menuAction())
        self.menubar.addAction(self.menuAnalyze.menuAction())
        self.menubar.addAction(self.menuSetting.menuAction())  # 添加 menuSetting 到菜单栏
        self.menubar.addAction(self.menuMoreInfo.menuAction())


        # 工具栏中的动作和滑动条
        self.actionAI = QtWidgets.QAction("AI😎", MainWindow)


        self.actionEditShapes = QtWidgets.QAction("Edit", MainWindow)
        self.actionEditShapes.setCheckable(True)

            # 初始化动作
        self.actionDuplicate = QtWidgets.QAction("Duplicate", MainWindow)
        self.actionDuplicate.setCheckable(False)
        self.actionDuplicate.setEnabled(False)  # 初始设置为不可用

        self.actionDelete = QtWidgets.QAction("Delete", MainWindow)
        self.actionDelete.setCheckable(False)
        self.actionDelete.setEnabled(False)  # 初始设置为不可用

        self.actionDeleteAllShapes = QtWidgets.QAction("Delete All Shapes", MainWindow)
        self.actionDeleteAllShapes.setCheckable(False)
        self.actionDeleteAllShapes.setEnabled(False)  # 初始设置为不可用

        self.actionUndo = QtWidgets.QAction("Undo", MainWindow)
        self.actionUndo.setCheckable(False)
        self.actionUndo.setEnabled(False)  # 初始设置为不可用

        self.actionGetMER= QtWidgets.QAction("Get MER", MainWindow)
        self.actionGetMER.setCheckable(False)
        self.actionGetMER.setEnabled(False)  # 初始设置为不可用

        self.actionFeatureExtraction = QtWidgets.QAction("Feature Extraction", MainWindow)
        self.actionFeatureExtraction.setCheckable(False)
        self.actionFeatureExtraction.setEnabled(False)





        self.actionZoom = QtWidgets.QAction("Fit to View", MainWindow)
        self.actionResetZoom = QtWidgets.QAction("Original Size", MainWindow)

        self.imageSizeLabel = QtWidgets.QLabel("Image Size: N/A; ")
        self.fileSizeLabel = QtWidgets.QLabel("File Size: N/A; ")
        self.mousePositionLabel = QtWidgets.QLabel("Mouse Position: N/A; ")
        self.pixelValueLabel = QtWidgets.QLabel("Pixel Value: N/A")

        # 创建 Create 子菜单动作
        self.actionCreatePolygon = QtWidgets.QAction("Create Polygon", MainWindow)
        self.actionCreateRotatedRectangle = QtWidgets.QAction("Create RotatedRectangle", MainWindow)
        self.actionCreateRectangle = QtWidgets.QAction("Create Rectangle", MainWindow)
        self.actionCreateLine = QtWidgets.QAction("Create Line", MainWindow)
        self.actionCreatePoint = QtWidgets.QAction("Create Point", MainWindow)

   
        # 创建 Create 工具按钮并添加子菜单
        self.createToolButton = QtWidgets.QToolButton(MainWindow)
        self.createToolButton.setText("Create")
        self.createToolButton.setPopupMode(QtWidgets.QToolButton.MenuButtonPopup)
        self.createMenu = QtWidgets.QMenu(self.createToolButton)
        self.createMenu.addAction(self.actionCreatePolygon)
        self.createMenu.addAction(self.actionCreateRotatedRectangle)
        self.createMenu.addAction(self.actionCreateRectangle)
        self.createMenu.addAction(self.actionCreateLine)
        self.createMenu.addAction(self.actionCreatePoint)
        self.createToolButton.setMenu(self.createMenu)
        self.createToolButton.setCheckable(True)

        # 将其他动作添加到工具栏
        self.toolBar.addAction(self.actionAI)

        # 将 Create 工具按钮添加到工具栏
        self.toolBar.addWidget(self.createToolButton)

        # 将其他动作添加到工具栏
        self.toolBar.addAction(self.actionEditShapes)
        self.toolBar.addAction(self.actionGetMER)
        self.toolBar.addAction(self.actionFeatureExtraction)
        self.toolBar.addAction(self.actionDuplicate)
        self.toolBar.addAction(self.actionDelete)
        
        self.toolBar.addAction(self.actionDeleteAllShapes)
        self.toolBar.addAction(self.actionUndo)
        self.toolBar.addAction(self.actionZoom)
        self.toolBar.addAction(self.actionResetZoom)

        self.zoomSlider = QtWidgets.QSlider(QtCore.Qt.Horizontal)
        self.zoomSlider.setObjectName("zoomSlider")
        self.zoomSlider.setMinimum(10)
        self.zoomSlider.setMaximum(1000)
        self.zoomSlider.setValue(100)  # 设置为范围的中间值

        self.zoomLineEdit = QtWidgets.QLineEdit("100%")
        self.zoomLineEdit.setFixedWidth(75)
        # self.zoomLineEdit.setValidator(QtGui.QIntValidator(10, 1000))  # 只允许输入整数

        self.toolBar.addWidget(self.zoomSlider)
        self.toolBar.addWidget(self.zoomLineEdit)


        self.toolBar.addWidget(self.imageSizeLabel)
        self.toolBar.addWidget(self.fileSizeLabel)
        self.toolBar.addWidget(self.mousePositionLabel)
        self.toolBar.addWidget(self.pixelValueLabel)

        # 创建 QActionGroup 实现互斥
        self.modeActionGroup = QActionGroup(MainWindow)
        self.modeActionGroup.setExclusive(True)
        self.modeActionGroup.addAction(self.actionEditShapes)
        self.modeActionGroup.addAction(self.actionCreateLine)
        self.modeActionGroup.addAction(self.actionCreatePoint)
        self.modeActionGroup.addAction(self.actionCreatePolygon)
        self.modeActionGroup.addAction(self.actionCreateRectangle)
        self.modeActionGroup.addAction(self.actionCreateRotatedRectangle)


        # 连接 Create 按钮的默认动作
        self.createToolButton.clicked.connect(self.default_create_polygon)

        # 连接 Create 工具按钮的菜单显示信号
        self.createToolButton.menu().aboutToHide.connect(self.update_create_toolbutton_state)


        self.actionEditShapes.toggled.connect(self.on_actionEditShapes_toggled)
        self.createToolButton.toggled.connect(self.on_createToolButton_toggled)
        # self.createToolButton.setEnabled(False)
        # self.actionEditShapes.setEnabled(False)

        self.retranslateUi(MainWindow)
        QtCore.QMetaObject.connectSlotsByName(MainWindow)

    
    def on_actionEditShapes_toggled(self, checked):
        if checked:
            # 取消选中 'create' 工具按钮
            self.createToolButton.setChecked(False)
 
    def on_createToolButton_toggled(self, checked):
        if checked:   
            self.actionEditShapes.setChecked(False)

        
    def createDockWidget(self, title):
        dock = QtWidgets.QDockWidget(title, self)
        dock.setObjectName(title)
        dock.setAllowedAreas(QtCore.Qt.LeftDockWidgetArea | QtCore.Qt.RightDockWidgetArea)
        contents = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(contents)
        #label = QtWidgets.QLabel(title, contents)  # 如果不需要显示标签，可以移除此行
        #layout.addWidget(label)
        contents.setLayout(layout)
        dock.setWidget(contents)
        self.addDockWidget(QtCore.Qt.RightDockWidgetArea, dock)

    def retranslateUi(self, MainWindow):
        _translate = QtCore.QCoreApplication.translate
        MainWindow.setWindowTitle(_translate("MainWindow", "Stoma Quant GUI"))
        self.menuFile.setTitle(_translate("MainWindow", "File"))
        self.menuView.setTitle(_translate("MainWindow", "View"))
        # self.menuImage.setTitle(_translate("MainWindow", "图像"))
        self.menuAnalyze.setTitle(_translate("MainWindow", "Analyze"))
        self.menuMoreInfo.setTitle(_translate("MainWindow", "More"))
        self.toolBar.setWindowTitle(_translate("MainWindow", "工具栏"))
        self.menuSetting.setTitle(_translate("MainWindow", "Settings"))
        self.actionShortcutHelp.setText(_translate("MainWindow", "Shortcut Keys Help"))



        self.actionOpen.setText(_translate("MainWindow", "Open Images"))
        self.actionSavePolygonAnnotataion.setText(_translate("MainWindow", "Save Polygon Annotation"))
        self.actionImportPolygonAnnotataion.setText(_translate("MainWindow", "Import Polygon Annotation"))
        self.actionSaveRectangleAnnotataion.setText(_translate("MainWindow", "Save Rectangle Annotation"))
        self.actionImportRectangleAnnotataion.setText(_translate("MainWindow", "Import Rectangle Annotation"))
        self.actionSaveRotatedRectangleAnnotataion.setText(_translate("MainWindow", "Save Rotated Rectangle Annotation"))
        self.actionImportRotatedRectangleAnnotataion.setText(_translate("MainWindow", "Import Rotated Rectangle Annotation"))
        self.actionShowPoint.setText(_translate("MainWindow", "All shapes are show in point"))
        self.actionShowID.setText(_translate("MainWindow", "hide/show shape ID"))
        self.actionColorSettings.setText(_translate("MainWindow", "Color Settings"))
        self.actionHeatMap.setText(_translate("MainWindow", "Heat Map of polygon features"))
        self.actionClose.setText(_translate("MainWindow", "Close"))
        # self.actionUndo.setText(_translate("MainWindow", "撤销"))
        # self.actionRedo.setText(_translate("MainWindow", "重做"))
        # self.actionAdjust.setText(_translate("MainWindow", "调整"))
        # self.actionProcess.setText(_translate("MainWindow", "处理"))
        self.actionGetMER.setText(_translate("MainWindow", "Get MER"))
        self.actionFeatureExtraction.setText(_translate("MainWindow", "Feature Extraction"))
        self.actionABorAD.setText(_translate("MainWindow", "AB or AD?"))
        # self.actionShapeFilter.setText(_translate("MainWindow", "Shape Filter"))
        self.actionSetMeasuringScale.setText(_translate("MainWindow", "Set Measuring Scale"))

        self.actionModelSetting.setText(_translate("MainWindow", "Model Setting"))
        self.actionBatchProcessing.setText(_translate("MainWindow", "Batch Processing"))

        # 替换现有的设置文本代码
        # self.actionBatchExport.setText(_translate("MainWindow", "Batch Export"))

        # 设置批量导出子菜单和动作的文本
        self.actionBatchExportPolygon.setText(_translate("MainWindow", "Batch Export Polygon annotations"))
        self.actionBatchExportRectangle.setText(_translate("MainWindow", "Batch Export Rectangle annotations"))
        self.actionBatchExportRotatedRectangle.setText(_translate("MainWindow", "Batch Export Rotated Rectangle annotations"))
        

        # 设置批量导出子菜单和动作的文本
        self.actionBatchImportPolygon.setText(_translate("MainWindow", "Batch Import Images and Polygon annotations"))
        self.actionBatchImportRectangle.setText(_translate("MainWindow", "Batch Import Images and Rectangle annotations"))
        self.actionBatchImportRotatedRectangle.setText(_translate("MainWindow", "Batch Import Images and Rotated Rectangle annotations"))

        self.actionInferenceSetting.setText(_translate("MainWindow", "Inference Setting"))

        self.actionCreatePolygon.setText(_translate("MainWindow", "Create Polygon"))
        self.actionCreateRotatedRectangle.setText(_translate("MainWindow", "Create RotatedRectangle"))
        self.actionCreateRectangle.setText(_translate("MainWindow", "Create Rectangle"))
        self.actionCreateLine.setText(_translate("MainWindow", "Create Line"))
        self.actionCreatePoint.setText(_translate("MainWindow", "Create Point"))


    def default_create_polygon(self):
        """
        当用户点击 Create 按钮主体时，触发默认的创建多边形动作。
        """
        self.actionCreatePolygon.trigger()





    def update_create_toolbutton_state(self):
        """
        当 Create 菜单关闭时，确保工具按钮保持选中状态。
        """
        if not self.createToolButton.menu().isVisible():
            self.createToolButton.setChecked(True)


if __name__ == "__main__":
    from PyQt5.QtWidgets import QApplication, QMainWindow
    import sys
    app = QApplication(sys.argv)
    app.setWindowIcon(QtGui.QIcon(r"ICON.png"))  # 设置应用程序图标
    # 设置全局字体
    font = QtGui.QFont("微软雅黑", 10)  # 设置为“微软雅黑”字体，字号为10
    app.setFont(font)

    GUI_Main = MainWindow()
    GUI_Main.setupUi(GUI_Main)
    GUI_Main.show()
    sys.exit(app.exec_())