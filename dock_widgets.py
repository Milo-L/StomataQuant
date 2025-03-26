# dock_widgets.py
import numpy as np
from PyQt5 import QtCore, QtGui, QtWidgets
from PyQt5.QtCore import Qt

# 在文件开头添加这个类定义
# 修改NumericTableWidgetItem的实现
class NumericTableWidgetItem(QtWidgets.QTableWidgetItem):
    def __lt__(self, other):
        try:
            # 尝试将文本转换为数值并比较
            return float(self.text()) < float(other.text())
        except (ValueError, TypeError):
            # 如果转换失败，尝试使用UserRole中的数据
            if (isinstance(self.data(QtCore.Qt.UserRole), (int, float)) and 
                isinstance(other.data(QtCore.Qt.UserRole), (int, float))):
                return self.data(QtCore.Qt.UserRole) < other.data(QtCore.Qt.UserRole)
            # 最后回退到默认的字符串比较
            return super().__lt__(other)
    

# 定义 ShapeListDock 类，继承自 QDockWidget。
class ShapeListDock(QtWidgets.QDockWidget):
    # 添加两个信号，用于通知可见性和选择状态的改变
    # 定义一个信号，用于通知可见性改变
    visibilityChanged = QtCore.pyqtSignal() 
     # 定义一个信号，用于通知选择状态改变，传递一个形状列表
    selectionClickedinShapeList = QtCore.pyqtSignal(list)

    def __init__(self, parent=None):
        super().__init__("ShapeList", parent)
        # 创建一个 QTableWidget，设置列数为 4，并设置列标题。
        self.table_widget = QtWidgets.QTableWidget()
        self.table_widget.setColumnCount(5)
        self.table_widget.setHorizontalHeaderLabels(['Visibility', 'Label', 'Group ID', 'Classnum',"shape_type"])
        # 设置最后一列自动拉伸
        self.table_widget.horizontalHeader().setStretchLastSection(True)
        # 启用排序功能
        self.table_widget.setSortingEnabled(True)  
        # 将表格添加到 dock 中
        self.setWidget(self.table_widget)
        # 保存形状列表
        self.shapes = []

        # 添加标志变量
        # self.updating_selection = False
       

          # 设置选择模式为多选
        self.table_widget.setSelectionMode(QtWidgets.QAbstractItemView.MultiSelection)
        self.table_widget.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
            
        self.table_widget.itemSelectionChanged.connect(self.on_shapelist_item_selected)
        # self.table_widget.itemChanged.connect(self.on_item_changed)  # 连接 itemChanged 信号

    
    def clearSelection(self):
        self.table_widget.clearSelection()

    def findItemByShape(self, shape):
        for row in range(self.table_widget.rowCount()):
            item = self.table_widget.item(row, 1)  # 假设第1列是 Label
            if item and id(item.data(QtCore.Qt.UserRole)) == id(shape):
                return row
        # 返回-1表示未找到，而不是抛出异常
        return -1
    
    def selectItem(self, row):
        selection_model = self.table_widget.selectionModel()
        selection_model.clearSelection()  # 清除之前的选择
        index = self.table_widget.model().index(row, 0)  # 假设第0列存在
        selection_model.select(index, QtCore.QItemSelectionModel.Select | QtCore.QItemSelectionModel.Rows)
    
    def selectItems(self, rows):
        selection_model = self.table_widget.selectionModel()
        selection_model.clearSelection()  # 清除之前的选择
        for row in rows:
            index = self.table_widget.model().index(row, 0)
            selection_model.select(index, QtCore.QItemSelectionModel.Select | QtCore.QItemSelectionModel.Rows)
    
    def scrollToItem(self, row):
        item = self.table_widget.item(row, 1)  # 假设第1列是 Label
        if item:
            self.table_widget.verticalScrollBar().setSliderPosition(row)
            self.table_widget.setFocus()
            # 处理事件以刷新界面
            QtWidgets.QApplication.processEvents()





# 填充表格数据
    def populate(self, shapes):
        self.table_widget.setSortingEnabled(False)  

        self.shapes = shapes
        self.table_widget.setRowCount(0)  # 清空现有内容

        for shape in shapes:
            row_position = self.table_widget.rowCount()
            self.table_widget.insertRow(row_position)

            # 创建复选框
            checkbox = QtWidgets.QCheckBox()
            checkbox.setChecked(shape.visible)
            # 使用 lambda 捕获当前的 shape
            checkbox.stateChanged.connect(lambda state, s=shape: self.on_visibility_changed(state, s))
            self.table_widget.setCellWidget(row_position, 0, checkbox)

            # 创建表格项
            label_item = QtWidgets.QTableWidgetItem(shape.label)
            
            # 使用NumericTableWidgetItem处理数值列
            group_id_item = NumericTableWidgetItem(str(shape.group_id))
            group_id_item.setData(QtCore.Qt.UserRole, float(shape.group_id) if isinstance(shape.group_id, (int, float)) else 0)
            
            classnum_item = NumericTableWidgetItem(str(shape.classnum))
            classnum_item.setData(QtCore.Qt.UserRole, float(shape.classnum) if isinstance(shape.classnum, (int, float)) else 0)
            
            shape_type_item = QtWidgets.QTableWidgetItem(str(shape.shape_type))

            # 设置文本对齐方式
            label_item.setTextAlignment(QtCore.Qt.AlignCenter)
            group_id_item.setTextAlignment(QtCore.Qt.AlignCenter)
            classnum_item.setTextAlignment(QtCore.Qt.AlignCenter)
            shape_type_item.setTextAlignment(QtCore.Qt.AlignCenter)

            # 设置文本颜色
            color = shape.get_color_by_classnum(shape.classnum)
            label_item.setForeground(color)
            group_id_item.setForeground(color)
            classnum_item.setForeground(color)
            shape_type_item.setForeground(color)

            # 将 shape 存储在表格项中
            for item in [label_item, group_id_item, classnum_item, shape_type_item]:
                item.setData(QtCore.Qt.UserRole, shape)
                item.setFlags(item.flags() & ~QtCore.Qt.ItemIsEditable | QtCore.Qt.ItemIsSelectable | QtCore.Qt.ItemIsEnabled)

            # 添加到表格中
            self.table_widget.setItem(row_position, 1, label_item)
            self.table_widget.setItem(row_position, 2, group_id_item)
            self.table_widget.setItem(row_position, 3, classnum_item)
            self.table_widget.setItem(row_position, 4, shape_type_item)

        self.table_widget.setSortingEnabled(True)

    # def on_item_changed(self, item):
    #     if item.column() == 1:  # Label 列
    #         shape = item.data(QtCore.Qt.UserRole)
    #         new_label = item.text()
    #         shape.label = new_label
    #         print(f"Shape label updated to: {new_label}")

# 当勾选可见性一列时，
# 更新形状的可见性状态。发射 visibilityChanged 信号。
    def on_visibility_changed(self, state, shape):
        shape.visible = (state == QtCore.Qt.Checked)
        self.visibilityChanged.emit()

# 当选择的行发生变化时， 更新形状的选中状态。获取所有选中的行。
# 收集选中的形状。发射 selectionChanged 信号
# 并传递选中的形状列表。
# 调用父对象的 on_shape_selected_in_dock 方法以更新画布。
# 实现通过在Dock表格中选择在画布中显示
   # dock_widgets.py

# 修改 on_shapelist_item_selected 方法
# 在 ShapeListDock 类的 __init__ 方法中连接信号
# self.table_widget.cellClicked.connect(self.on_shapelist_item_selected)

    # 重写 on_shapelist_item_selected 方法
    def on_shapelist_item_selected(self):
        parent = self.parent()
        if parent._noCanvasSelectionSlot:
            pass
        else:
            selected_rows = self.table_widget.selectionModel().selectedRows()
            selected_shapes = []
            
            for index in selected_rows:
                row = index.row()
                item = self.table_widget.item(row, 1)  # 假设第2列是 Label
                if item:
                    shape = item.data(QtCore.Qt.UserRole)
                    if shape:
                        selected_shapes.append(shape)
            # 发射信号通知主窗口更新 Canvas
            self.selectionClickedinShapeList.emit(selected_shapes)


    
    def update_visibility(self):
        for row, shape in enumerate(self.shapes):
            checkbox = self.table_widget.cellWidget(row, 0)
            if checkbox:
                checkbox.blockSignals(True)
                checkbox.setChecked(shape.visible)
                checkbox.blockSignals(False)
        self.table_widget.repaint()
        self.table_widget.viewport().update()

    def add_shape(self, shape):
        """向形状列表中添加新形状"""
        # 插入新行
        row_position = self.table_widget.rowCount()
        self.table_widget.insertRow(row_position)

        # 创建复选框
        checkbox = QtWidgets.QCheckBox()
        checkbox.setChecked(shape.visible)
        checkbox.stateChanged.connect(lambda state, s=shape: self.on_visibility_changed(state, s))
        self.table_widget.setCellWidget(row_position, 0, checkbox)

        # 添加标签
        label_item = QtWidgets.QTableWidgetItem(str(shape.label))
        label_item.setData(QtCore.Qt.UserRole, shape)  # 存储shape对象引用
        self.table_widget.setItem(row_position, 1, label_item)

        # 添加Group ID - 使用NumericTableWidgetItem
        group_id_item = NumericTableWidgetItem(str(shape.group_id))
        group_id_item.setData(QtCore.Qt.UserRole, float(shape.group_id) if isinstance(shape.group_id, (int, float)) else 0)
        group_id_item.setData(QtCore.Qt.UserRole+1, shape)  # 继续存储shape对象引用
        self.table_widget.setItem(row_position, 2, group_id_item)

        # 添加Classnum - 使用NumericTableWidgetItem
        classnum_item = NumericTableWidgetItem(str(shape.classnum))
        classnum_item.setData(QtCore.Qt.UserRole, float(shape.classnum) if isinstance(shape.classnum, (int, float)) else 0)
        classnum_item.setData(QtCore.Qt.UserRole+1, shape)  # 继续存储shape对象引用
        self.table_widget.setItem(row_position, 3, classnum_item)

        # 添加shape_type
        shape_type_item = QtWidgets.QTableWidgetItem(str(shape.shape_type))
        shape_type_item.setData(QtCore.Qt.UserRole, shape)  # 存储shape对象引用
        self.table_widget.setItem(row_position, 4, shape_type_item)

        # 更新shapes列表
        if shape not in self.shapes:
            self.shapes.append(shape)


        
# 定义 LabelListDock 类，继承自 QDockWidget。
class LabelListDock(QtWidgets.QDockWidget):
    visibilityChanged = QtCore.pyqtSignal(str, bool)  # 传递标签和可见性状态

    def __init__(self, parent=None):
        super().__init__("LabelList", parent)

        self.table_widget = QtWidgets.QTableWidget()
        self.table_widget.setColumnCount(2)
        self.table_widget.setHorizontalHeaderLabels(['Visible', 'Label'])
        self.table_widget.horizontalHeader().setStretchLastSection(True)
        self.table_widget.setSortingEnabled(True)
        self.setWidget(self.table_widget)
        self.labels = []
        # 存储标签与对应的复选框
        self.checkbox_dict = {}  # 初始化为实例变量

# 填充表格数据
# 填充表格数据
    # def populate(self, shapes, get_color_func):
    #     self.labels.clear()
    #     self.table_widget.setRowCount(0)
    #     # 使用字典存储标签的选中状态，而不是 QCheckBox 实例
    #     # self.checkbox_dict.clear()  # 保留现有的选中状态

    #     label_set = set(shape.label for shape in shapes)
    #     label_set = {label for label in label_set if label is not None}
    #     for row, label in enumerate(sorted(label_set)):
    #         self.table_widget.insertRow(row)

    #         # 创建复选框
    #         checkbox = QtWidgets.QCheckBox()
    #         # 设置复选框状态，如果之前有记录则使用记录的状态，否则默认选中
    #         checked = self.checkbox_dict.get(label, True)
    #         if isinstance(checked, QtWidgets.QCheckBox):
    #         # 如果不小心存储了 QCheckBox，重置为默认值
    #             checked = True
    #         checkbox.setChecked(checked)
    #         # 连接信号以更新 checkbox_dict 中的状态
    #         checkbox.stateChanged.connect(lambda state, l=label: self.on_visibility_changed(state, l))
    #         self.table_widget.setCellWidget(row, 0, checkbox)

    #         # 更新 checkbox_dict 中的选中状态
    #         self.checkbox_dict[label] = checkbox.isChecked()
    def populate(self, shapes, get_color_func):
        self.labels.clear()
        self.table_widget.setRowCount(0)
        # 使用字典存储标签的选中状态，而不是 QCheckBox 实例
        # self.checkbox_dict.clear()  # 保留现有的选中状态

        # 计算每个标签的可见状态
        label_visibility = {}
        for shape in shapes:
            if shape.label is not None:
                # 如果标签首次出现，初始化为该形状的可见性
                if shape.label not in label_visibility:
                    label_visibility[shape.label] = shape.visible
                # 如果任何形状可见，则该标签为可见
                elif shape.visible:
                    label_visibility[shape.label] = True

        label_set = set(shape.label for shape in shapes)
        label_set = {label for label in label_set if label is not None}
        for row, label in enumerate(sorted(label_set)):
            self.table_widget.insertRow(row)

            # 创建复选框
            checkbox = QtWidgets.QCheckBox()
            
            # 首先检查当前画布中该标签的可见性
            if label in label_visibility:
                # 使用该标签对应形状的可见性状态
                checked = label_visibility[label]
            else:
                # 如果在当前画布中找不到该标签，则使用之前保存的状态或默认为True
                checked = self.checkbox_dict.get(label, True)
                if isinstance(checked, QtWidgets.QCheckBox):
                    # 如果不小心存储了 QCheckBox，重置为默认值
                    checked = True
                    
            checkbox.setChecked(checked)
            # 连接信号以更新 checkbox_dict 中的状态
            checkbox.stateChanged.connect(lambda state, l=label: self.on_visibility_changed(state, l))
            self.table_widget.setCellWidget(row, 0, checkbox)

            # 更新 checkbox_dict 中的选中状态
            self.checkbox_dict[label] = checked  # 保存实际的布尔值而不是checkbox的状态

            # ... 其余代码不变

            # 创建标签项
            label_item = QtWidgets.QTableWidgetItem(label)
            label_item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)  # 设置为只读
            classnum = next((shape.classnum for shape in shapes if shape.label == label), None)
            color = get_color_func(classnum)
            label_item.setForeground(color)
            self.table_widget.setItem(row, 1, label_item)

# 当勾选可见性一列时，更新标签的可见性状态。发射 visibilityChanged 信号。
# 在 LabelListDock 类中
    def on_visibility_changed(self, state, label):
        visible = (state == QtCore.Qt.Checked)
        self.visibilityChanged.emit(label, visible)

    def add_label(self, label):
        """添加新标签到标签列表"""
        # 检查标签是否已存在
        for row in range(self.table_widget.rowCount()):
            if self.table_widget.item(row, 1).text() == label:
                return

        # 插入新行
        row = self.table_widget.rowCount()
        self.table_widget.insertRow(row)

        # 创建复选框
        checkbox = QtWidgets.QCheckBox()
        checkbox.setChecked(True)  # 默认可见
        checkbox.stateChanged.connect(lambda state, l=label: self.on_visibility_changed(state, l))
        self.table_widget.setCellWidget(row, 0, checkbox)
        self.checkbox_dict[label] = checkbox

        # 创建标签项
        label_item = QtWidgets.QTableWidgetItem(label)
        self.table_widget.setItem(row, 1, label_item)

            
        # 更新标签列表
        if label not in self.labels:
            self.labels.append(label)




class MeasuredResultsDock(QtWidgets.QDockWidget):
    def __init__(self, parent=None):
        super().__init__("MeasuredResults(Shapes)", parent)
        self.tab_widget = QtWidgets.QTabWidget()
        self.setWidget(self.tab_widget)

        # 创建用于不同形状的 QTableWidget
        self.polygon_table = QtWidgets.QTableWidget()
        self.rotated_rectangle_table = QtWidgets.QTableWidget()
        self.rectangle_table = QtWidgets.QTableWidget()
        self.line_table = QtWidgets.QTableWidget()
        self.point_table = QtWidgets.QTableWidget()

        # 将表格添加到选项卡
        self.tab_widget.addTab(self.polygon_table, "Polygon")
        self.tab_widget.addTab(self.rotated_rectangle_table, "Rotated Rectangle")
        self.tab_widget.addTab(self.rectangle_table, "Rectangle")
        self.tab_widget.addTab(self.line_table, "Line")
        self.tab_widget.addTab(self.point_table, "Point")

        # 设置表格属性
        self.setup_table(self.polygon_table)
        self.setup_table(self.rotated_rectangle_table)
        self.setup_table(self.rectangle_table)
        self.setup_table(self.line_table)
        self.setup_table(self.point_table)
        #         # 初始化排序状态字典
        # self.sort_order = {}

    def setup_table(self, table):
        table.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        table.setSelectionBehavior(QtWidgets.QTableWidget.SelectRows)
        table.horizontalHeader().setStretchLastSection(True)
        table.setSelectionMode(QtWidgets.QAbstractItemView.MultiSelection)  # 支持多选
        # Add context menu
        table.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        table.customContextMenuRequested.connect(lambda pos: self.create_context_menu(table, pos))
        # Add shortcut Ctrl+A
        select_all_shortcut = QtWidgets.QShortcut(QtGui.QKeySequence("Ctrl+A"), table)
        select_all_shortcut.activated.connect(lambda: self.toggle_select_all(table))
        # Add copy action
        copy_action = QtWidgets.QAction("Copy", table)
        copy_action.triggered.connect(lambda: self.copy_selected_rows(table))
        table.addAction(copy_action)
        # 启用内置排序功能
        table.setSortingEnabled(True)

#         table.horizontalHeader().sectionClicked.connect(lambda index: self.sort_table(table, index))
# ### 排序功能
#     def sort_table(self, table, column):
#         # 获取当前排序顺序，默认升序
#         ascending = self.sort_order.get(table, {}).get(column, True)
#         # 切换排序顺序
#         self.sort_order.setdefault(table, {})[column] = not ascending

#         table.sortItems(column, QtCore.Qt.AscendingOrder if ascending else QtCore.Qt.DescendingOrder)

#         rows = []
#         for row in range(table.rowCount()):
#             items = []
#             for col in range(table.columnCount()):
#                 item = table.item(row, col)
#                 if item is not None:
#                     items.append(item.text())
#                 else:
#                     items.append('')
#             rows.append(items)
        
#         # 判断列类型
#         is_numeric = True
#         for row in rows:
#             try:
#                 float(row[column])
#             except ValueError:
#                 is_numeric = False
#                 break
        
#         if is_numeric:
#             rows.sort(key=lambda x: float(x[column]) if x[column] else 0)
#         else:
#             rows.sort(key=lambda x: (x[column].lower(), float(''.join(filter(str.isdigit, x[column])))) if any(char.isdigit() for char in x[column]) else x[column].lower())
        
#         table.setRowCount(0)
#         for row_data in rows:
#             row_position = table.rowCount()
#             table.insertRow(row_position)
#             for col, data in enumerate(row_data):
#                 table.setItem(row_position, col, QtWidgets.QTableWidgetItem(data))

    def create_context_menu(self, table, position):
        menu = QtWidgets.QMenu()
        copy_action = menu.addAction("Copy")
        delete_action = menu.addAction("Delete")
        select_all_action = menu.addAction("Select All")
        save_as_action = menu.addAction("Save As")
        action = menu.exec_(table.viewport().mapToGlobal(position))
        if action == copy_action:
            self.copy_selected_rows(table)
        elif action == delete_action:
            self.delete_selected_rows(table)
        elif action == select_all_action:
            self.toggle_select_all(table)
        elif action == save_as_action:
            self.save_table_as(table)

    def copy_selected_rows(self, table):
        if isinstance(table, QtWidgets.QTableWidget):
            selected_rows = sorted(set(index.row() for index in table.selectedIndexes()))
            if selected_rows:
                data = []
                headers = [table.horizontalHeaderItem(col).text() for col in range(table.columnCount())]
                data.append('\t'.join(headers))  # 添加表头
                for row in selected_rows:
                    row_data = []
                    for column in range(table.columnCount()):
                        item = table.item(row, column)
                        if item:
                            row_data.append(item.text())
                        else:
                            row_data.append('')
                    data.append('\t'.join(row_data))
                clipboard = QtWidgets.QApplication.clipboard()
                clipboard.setText('\n'.join(data))
        else:
            print("Selected widget is not a QTableWidget.--- by copy_selected_rows method")


        
    def delete_selected_rows(self, table):
        if isinstance(table, QtWidgets.QTableWidget):
            selected_rows = sorted(set(index.row() for index in table.selectedIndexes()), reverse=True)
            for row in selected_rows:
                table.removeRow(row)
        else:
            print("Selected widget is not a QTableWidget. --- by delete_selected_rows method")

    def toggle_select_all(self, table):
        if isinstance(table, QtWidgets.QTableWidget):
            if table.selectionModel().hasSelection():
                table.clearSelection()
            else:
                table.selectAll()
        else:
            print("Selected widget is not a QTableWidget.--- by toggle_select_all method")

    def save_table_as(self, table):
        if isinstance(table, QtWidgets.QTableWidget):
            # 获取当前图片名称、QDockWidget名称和QtWidgets名称
            # current_image_name = self.get_current_image_name()  # 需要实现此方法
            # dock_widget_name = table.parent().windowTitle() if table.parent() else "DockWidget"
            # widget_name = table.objectName() if table.objectName() else "Table"
            default_filename = f"Results.csv"
            
            path, _ = QtWidgets.QFileDialog.getSaveFileName(
                table, 
                "Save Table", 
                default_filename, 
                "CSV Files (*.csv);;All Files (*)"
            )
            if path:
                with open(path, 'w', encoding='utf-8') as file:
                    # 写入表头
                    headers = [table.horizontalHeaderItem(col).text() for col in range(table.columnCount())]
                    file.write(','.join(headers) + '\n')
                    for row in range(table.rowCount()):
                        row_data = []
                        for column in range(table.columnCount()):
                            item = table.item(row, column)
                            if item:
                                row_data.append(item.text())
                            else:
                                row_data.append('')
                        file.write(','.join(row_data) + '\n')
        else:
            print("Selected widget is not a QTableWidget.---by save_table_as method")

    def populate(self, shapes):
        # 清空所有表格
        self.clear_tables()
        self.polygon_table.setSortingEnabled(False)
        self.rotated_rectangle_table.setSortingEnabled(False)
        self.rectangle_table.setSortingEnabled(False)
        self.line_table.setSortingEnabled(False)
        self.point_table.setSortingEnabled(False)
        # 按形状类型分类
        shape_groups = {
            'polygon': [],
            'rotated_rectangle': [],
            'rectangle': [],
            'line': [],
            'point': [],
        }

        for shape in shapes:
            if hasattr(shape, 'feature_results'):
                shape_type = shape.shape_type
                if shape_type in shape_groups:
                    shape_groups[shape_type].append(shape)

        # 分别填充不同的表格
        self.populate_polygon_table(shape_groups['polygon'])
        self.populate_rotated_rectangle_table(shape_groups['rotated_rectangle'])
        self.populate_rectangle_table(shape_groups['rectangle'])
        self.populate_line_table(shape_groups['line'])
        self.populate_point_table(shape_groups['point'])

        
        self.polygon_table.setSortingEnabled(True)
        self.rotated_rectangle_table.setSortingEnabled(True)
        self.rectangle_table.setSortingEnabled(True)
        self.line_table.setSortingEnabled(True)
        self.point_table.setSortingEnabled(True)

    def clear_tables(self):
        self.polygon_table.setRowCount(0)
        self.rotated_rectangle_table.setRowCount(0)
        self.rectangle_table.setRowCount(0)
        self.line_table.setRowCount(0)
        self.point_table.setRowCount(0)

    def populate_polygon_table(self, shapes):
        if not shapes:
            return

        # 假设所有形状单位相同，取第一个
        unit = shapes[0].unit if hasattr(shapes[0], 'unit') else 'pixel'
        area_unit = f" ({unit}²)" if unit else 'pixel²'
        length_unit = f" ({unit})" if unit else 'pixel'

        headers = [
            'Label', 'Group ID',
            f'Area{area_unit}',
            f'Perimeter{length_unit}',
            f'MER Length{length_unit}',

            f'MER Width{length_unit}',
            'Circularity',
            'Eccentricity',
            f'ACH',
            f'PCH',
            'Roundness', 'Convexity', 'Solidity','Center Point' 
        ]
        self.polygon_table.setColumnCount(len(headers))
        self.polygon_table.setHorizontalHeaderLabels(headers)

        for shape in shapes:
            results = shape.feature_results
            if not isinstance(results, dict):
                print(f"警告: feature_results 不是字典类型: {results}")
                continue

            row_position = self.polygon_table.rowCount()
            self.polygon_table.insertRow(row_position)
            for col_index, key in enumerate(results.keys()):
                value = results.get(key, '')
                # item = QtWidgets.QTableWidgetItem(f"{value:.4f}" if isinstance(value, float) else str(value))
                if isinstance(value, (int, float)):
                    item = NumericTableWidgetItem(f"{value:.4f}" if isinstance(value, float) else str(value))
                    item.setData(QtCore.Qt.UserRole, float(value))  # 存储实际数值
                else:
                    item = QtWidgets.QTableWidgetItem(str(value))
                self.polygon_table.setItem(row_position, col_index, item)

    def populate_rotated_rectangle_table(self, shapes):
        if not shapes:
            return

        unit = shapes[0].unit if hasattr(shapes[0], 'unit') else 'pixel'
        # area_unit = f" ({unit}²)" if unit else 'pixel²'
        length_unit = f" ({unit})" if unit else 'pixel'

        headers = [
            'Label', 
            'Group ID',
            f'Width{length_unit}',
            f'Length{length_unit}',
            'Aspect Ratio',
            'Angle','Center Point' 
        ]
        self.rotated_rectangle_table.setColumnCount(len(headers))
        self.rotated_rectangle_table.setHorizontalHeaderLabels(headers)

        for shape in shapes:
            results = shape.feature_results
            if not isinstance(results, dict):
                print(f"警告: feature_results 不是字典类型: {results}")
                continue

            row_position = self.rotated_rectangle_table.rowCount()
            self.rotated_rectangle_table.insertRow(row_position)
            for col_index, key in enumerate(results.keys()):
                value = results.get(key, '')
                # item = QtWidgets.QTableWidgetItem(f"{value:.4f}" if isinstance(value, float) else str(value))
                # item = QtWidgets.QTableWidgetItem(f"{value:.4f}" if isinstance(value, float) else str(value))
                if isinstance(value, (int, float)):
                    item = NumericTableWidgetItem(f"{value:.4f}" if isinstance(value, float) else str(value))
                    item.setData(QtCore.Qt.UserRole, float(value))  # 存储实际数值
                else:
                    item = QtWidgets.QTableWidgetItem(str(value))
                self.rotated_rectangle_table.setItem(row_position, col_index, item)

    
    def populate_line_table(self, shapes):
        if not shapes:
            return

        unit = shapes[0].unit if hasattr(shapes[0], 'unit') else 'pixel'
        length_unit = f" ({unit})" if unit else 'pixel'

        headers = [
            'Label', 
            'Group ID',
            f'Length{length_unit}',
            'StartPoint',
            'EndPoint',
            'Angle','Center Point' 
        ]
        self.line_table.setColumnCount(len(headers))
        self.line_table.setHorizontalHeaderLabels(headers)

        for shape in shapes:
            results = shape.feature_results
            if not isinstance(results, dict):
                print(f"警告: feature_results 不是字典类型: {results}")
                continue
            row_position = self.line_table.rowCount()
            self.line_table.insertRow(row_position)
            for col_index, key in enumerate(results.keys()):
                value = results.get(key, '')
                # item = QtWidgets.QTableWidgetItem(f"{value:.4f}" if isinstance(value, float) else str(value))
                # item = QtWidgets.QTableWidgetItem(f"{value:.4f}" if isinstance(value, float) else str(value))
                if isinstance(value, (int, float)):
                    item = NumericTableWidgetItem(f"{value:.4f}" if isinstance(value, float) else str(value))
                    item.setData(QtCore.Qt.UserRole, float(value))  # 存储实际数值
                else:
                    item = QtWidgets.QTableWidgetItem(str(value))
                self.line_table.setItem(row_position, col_index, item)

    def populate_rectangle_table(self, shapes):
        if not shapes:
            return

        unit = shapes[0].unit if hasattr(shapes[0], 'unit') else 'pixel'
        # area_unit = f" ({unit}²)" if unit else ''
        length_unit = f" ({unit})" if unit else 'pixel'


        headers = [
            'Label', 
            'Group ID',
            f'Width{length_unit}',    
            f'Length{length_unit}',
            'Aspect Ratio',
            'Center Point'  # 添加中心点列
        ]

        self.rectangle_table.setColumnCount(len(headers))
        self.rectangle_table.setHorizontalHeaderLabels(headers)

        for shape in shapes:
            row_position = self.rectangle_table.rowCount()
            self.rectangle_table.insertRow(row_position)

            results = shape.feature_results
            if not isinstance(results, dict):
                print(f"警告: feature_results 不是字典类型: {results}")
                continue
            for col_index, key in enumerate(results.keys()):
                value = results.get(key, '')
                # item = QtWidgets.QTableWidgetItem(f"{value:.4f}" if isinstance(value, float) else str(value))
                # item = QtWidgets.QTableWidgetItem(f"{value:.4f}" if isinstance(value, float) else str(value))
                if isinstance(value, (int, float)):
                    item = NumericTableWidgetItem(f"{value:.4f}" if isinstance(value, float) else str(value))
                    item.setData(QtCore.Qt.UserRole, float(value))  # 存储实际数值
                else:
                    item = QtWidgets.QTableWidgetItem(str(value))
                self.rectangle_table.setItem(row_position, col_index, item)


    def populate_point_table(self, shapes):
        if not shapes:
            return



        headers = [
            'Label', 'Group ID',
            f'X',
            f'Y'
        ]
        self.point_table.setColumnCount(len(headers))
        self.point_table.setHorizontalHeaderLabels(headers)

        for shape in shapes:
            results = shape.feature_results
            if not isinstance(results, dict):
                print(f"警告: feature_results 不是字典类型: {results}")
                continue
            row_position = self.point_table.rowCount()
            self.point_table.insertRow(row_position)
            for col_index, key in enumerate(results.keys()):
                value = results.get(key, '')
                # item = QtWidgets.QTableWidgetItem(f"{value:.4f}" if isinstance(value, float) else str(value))
                # item = QtWidgets.QTableWidgetItem(f"{value:.4f}" if isinstance(value, float) else str(value))
                if isinstance(value, (int, float)):
                    item = NumericTableWidgetItem(f"{value:.4f}" if isinstance(value, float) else str(value))
                    item.setData(QtCore.Qt.UserRole, float(value))  # 存储实际数值
                else:
                    item = QtWidgets.QTableWidgetItem(str(value))
                self.point_table.setItem(row_position, col_index, item)




class ImageResultsSummaryDock(QtWidgets.QDockWidget):
    def __init__(self, parent=None):
        super().__init__("ResultsSummary(Image)", parent)
        self.tab_widget = QtWidgets.QTabWidget()
        self.setWidget(self.tab_widget)

        # 创建包含六个选项卡的 tab_widget

        self.summary_table = QtWidgets.QTableWidget()
        self.polygon_table = QtWidgets.QTableWidget()
        self.rotated_rectangle_table = QtWidgets.QTableWidget()
        self.rectangle_table = QtWidgets.QTableWidget()
        self.line_table = QtWidgets.QTableWidget()
        self.point_table = QtWidgets.QTableWidget()

        # 添加选项卡
        self.tab_widget.addTab(self.summary_table, "Summary")
        self.tab_widget.addTab(self.polygon_table, "Polygon")
        self.tab_widget.addTab(self.rotated_rectangle_table, "Rotated Rectangle")
        self.tab_widget.addTab(self.rectangle_table, "Rectangle")
        self.tab_widget.addTab(self.line_table, "Line")
        self.tab_widget.addTab(self.point_table, "Point")

        # 设置主要部件
        self.setWidget(self.tab_widget)

        # 设置表格
        self.setup_table(self.summary_table)
        self.setup_table(self.polygon_table)
        self.setup_table(self.rotated_rectangle_table)
        self.setup_table(self.rectangle_table)
        self.setup_table(self.line_table)
        self.setup_table(self.point_table)  

        self.setup_summary_table()
        self.setup_feature_tables()

        #     # 初始化排序状态字典
        # self.sort_order = {}


    def setup_table(self, table):
        table.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        table.setSelectionBehavior(QtWidgets.QTableWidget.SelectRows)
        table.horizontalHeader().setStretchLastSection(True)
        table.setSelectionMode(QtWidgets.QAbstractItemView.MultiSelection)  # 支持多选
        # Add context menu
        table.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        table.customContextMenuRequested.connect(lambda pos: self.create_context_menu(table, pos))
        # Add shortcut Ctrl+A
        select_all_shortcut = QtWidgets.QShortcut(QtGui.QKeySequence("Ctrl+A"), table)
        select_all_shortcut.activated.connect(lambda: self.toggle_select_all(table))
        # Add copy action
        copy_action = QtWidgets.QAction("Copy", table)
        copy_action.triggered.connect(lambda: self.copy_selected_rows(table))
        table.addAction(copy_action)
        # 启用内置排序功能
        table.setSortingEnabled(True)
#         table.horizontalHeader().sectionClicked.connect(lambda index: self.sort_table(self.summary_table, index))
# ### 排序功能
#     def sort_table(self, table, column):
#             # 获取当前排序顺序，默认升序
#         ascending = self.sort_order.get(table, {}).get(column, True)
#         # 切换排序顺序
#         self.sort_order.setdefault(table, {})[column] = not ascending

#         table.sortItems(column, QtCore.Qt.AscendingOrder if ascending else QtCore.Qt.DescendingOrder)

#         rows = []
#         for row in range(table.rowCount()):
#             items = []
#             for col in range(table.columnCount()):
#                 item = table.item(row, col)
#                 if item is not None:
#                     items.append(item.text())
#                 else:
#                     items.append('')
#             rows.append(items)
        
#         # 判断列类型
#         is_numeric = True
#         for row in rows:
#             try:
#                 float(row[column])
#             except ValueError:
#                 is_numeric = False
#                 break
        
#         if is_numeric:
#             rows.sort(key=lambda x: float(x[column]) if x[column] else 0)
#         else:
#             rows.sort(key=lambda x: (x[column].lower(), float(''.join(filter(str.isdigit, x[column])))) if any(char.isdigit() for char in x[column]) else x[column].lower())
        
#         table.setRowCount(0)
#         for row_data in rows:
#             row_position = table.rowCount()
#             table.insertRow(row_position)
#             for col, data in enumerate(row_data):
#                 table.setItem(row_position, col, QtWidgets.QTableWidgetItem(data))

    def create_context_menu(self, table, position):
        menu = QtWidgets.QMenu()
        copy_action = menu.addAction("Copy")
        delete_action = menu.addAction("Delete")
        select_all_action = menu.addAction("Select All")
        save_as_action = menu.addAction("Save As")
        action = menu.exec_(table.viewport().mapToGlobal(position))
        if action == copy_action:
            self.copy_selected_rows(table)
        elif action == delete_action:
            self.delete_selected_rows(table)
        elif action == select_all_action:
            self.toggle_select_all(table)
        elif action == save_as_action:
            self.save_table_as(table)

    def copy_selected_rows(self, table):
        if isinstance(table, QtWidgets.QTableWidget):
            selected_rows = sorted(set(index.row() for index in table.selectedIndexes()))
            if selected_rows:
                data = []
                headers = [table.horizontalHeaderItem(col).text() for col in range(table.columnCount())]
                data.append('\t'.join(headers))  # 添加表头
                for row in selected_rows:
                    row_data = []
                    for column in range(table.columnCount()):
                        item = table.item(row, column)
                        if item:
                            row_data.append(item.text())
                        else:
                            row_data.append('')
                    data.append('\t'.join(row_data))
                clipboard = QtWidgets.QApplication.clipboard()
                clipboard.setText('\n'.join(data))
        else:
            print("Selected widget is not a QTableWidget.--- by copy_selected_rows method")
    
   
    def delete_selected_rows(self, table):
        if isinstance(table, QtWidgets.QTableWidget):
            selected_rows = sorted(set(index.row() for index in table.selectedIndexes()), reverse=True)
            for row in selected_rows:
                table.removeRow(row)
        else:
            print("Selected widget is not a QTableWidget.--- by delete_selected_rows method")

    def toggle_select_all(self, table):
        if isinstance(table, QtWidgets.QTableWidget):
            if table.selectionModel().hasSelection():
                table.clearSelection()
            else:
                table.selectAll()
        else:
            print("Selected widget is not a QTableWidget. --- by toggle_select_all method")

    def save_table_as(self, table):
        if isinstance(table, QtWidgets.QTableWidget):
            # 获取当前图片名称、QDockWidget名称和QtWidgets名称
            # # current_image_name = self.get_current_image_name()  # 需要实现此方法
            # dock_widget_name = table.parent().windowTitle() if table.parent() else "DockWidget"
            # widget_name = table.objectName() if table.objectName() else "Table"
            default_filename = f"Result.csv"

            
            path, _ = QtWidgets.QFileDialog.getSaveFileName(
                table, 
                "Save Table", 
                default_filename, 
                "CSV Files (*.csv);;All Files (*)"
            )
            if path:
                with open(path, 'w', encoding='utf-8') as file:
                    # 写入表头
                    headers = [table.horizontalHeaderItem(col).text() for col in range(table.columnCount())]
                    file.write(','.join(headers) + '\n')
                    for row in range(table.rowCount()):
                        row_data = []
                        for column in range(table.columnCount()):
                            item = table.item(row, column)
                            if item:
                                row_data.append(item.text())
                            else:
                                row_data.append('')
                        file.write(','.join(row_data) + '\n')
        else:
            print("Selected widget is not a QTableWidget.---by save_table_as method")




    def setup_summary_table(self):

        # 设置 Summary 表格的表头
        self.summary_table.setColumnCount(5)
        self.summary_table.setHorizontalHeaderLabels(['Label', 'Shape Type', 'Num', 'Density', 'Image Area'])
        
    def setup_feature_tables(self):
        # 为每个形状类型的表格设置表头
        headers = ['Feature', 'Num', 'Average', 'Std Dev', 'Median', 'Min', 'Max']
        tables = [self.polygon_table, self.rotated_rectangle_table, self.rectangle_table, self.line_table, self.point_table]
        for table in tables:
            table.setColumnCount(7)
            table.setHorizontalHeaderLabels(headers)

    def populate(self, shapes, image_width, image_height, scale_info=None):
        # 使用形状数据填充表格
        
        self.populate_summary_table(shapes, image_width, image_height, scale_info)

        if any(shape.feature_results for shape in shapes):
            self.populate_feature_tables(shapes)
        else:
            self.populate_feature_tables([])

    def populate_summary_table(self, shapes, image_width, image_height, scale_info=None):
        self.summary_table.setRowCount(0)  # 清空现有内容


        # 计算图像面积
        if scale_info:
            # 假设 scale_info 中的 'scale_factor' 是 每单位长度的像素数
            scale = scale_info.get('scale', 1.0)
            width_in_units = image_width * scale
            height_in_units = image_height * scale
            image_area = width_in_units * height_in_units
            area_unit = f"{scale_info.get('unit', 'pixel')}²"
            density_unit = f"n/{area_unit}"
        else:
            # 使用像素
            image_area = image_width * image_height
            area_unit = 'pixels²'
            density_unit = f"n/{area_unit}"

        # 收集每个 (label, shape_type) 的计数
        summary = {}
        for shape in shapes:
            key = (shape.label, shape.shape_type)
            if key not in summary:
                summary[key] = 1
            else:
                summary[key] +=1

        # 填充表格
        for (label, shape_type), num in summary.items():
            density = num / image_area
            row_position = self.summary_table.rowCount()
            self.summary_table.insertRow(row_position)

            # Label
            label_item = QtWidgets.QTableWidgetItem(str(label))
            self.summary_table.setItem(row_position, 0, label_item)

            # Shape Type
            shape_type_item = QtWidgets.QTableWidgetItem(str(shape_type))
            self.summary_table.setItem(row_position, 1, shape_type_item)

            # Num
            num_item = QtWidgets.QTableWidgetItem(str(num))
            self.summary_table.setItem(row_position, 2, num_item)

            # Density
            density_item = QtWidgets.QTableWidgetItem(f"{density:.3e} {density_unit}")
            self.summary_table.setItem(row_position, 3, density_item)

            # Image Area
            area_item = QtWidgets.QTableWidgetItem(f"{image_area:.4f} {area_unit}")
            self.summary_table.setItem(row_position, 4, area_item)

    def populate_feature_tables(self, shapes):
        # 初始化每个形状类型的特征列表
        shape_type_tables = {
            'polygon': self.polygon_table,
            'rotated_rectangle': self.rotated_rectangle_table,
            'rectangle': self.rectangle_table,
            'line': self.line_table,
            'point': self.point_table,
        }
        shape_type_features = {
            'polygon': [],
            'rotated_rectangle': [],
            'rectangle': [],
            'line': [],
            'point': [],
        }

        # 收集每个形状的特征
        for shape in shapes:
            features = shape.feature_results
            shape_type = shape.shape_type
            if shape_type in shape_type_features:
                shape_type_features[shape_type].append(features)

        # 对每个形状类型，计算统计量并填充表格
        for shape_type, features_list in shape_type_features.items():
            table = shape_type_tables[shape_type]
            self.populate_feature_table(table, features_list)

    def populate_feature_table(self, table, features_list):
        # 清空表格
        table.setRowCount(0)

        if not features_list:
            return

        # 获取特征名称列表
        feature_names = list(features_list[0].keys())
        # 移除非数值特征
        non_numeric_features = ['Label', 'Group ID', 'Center Point','Start Point','End Point']
        for name in non_numeric_features:
            if name in feature_names:
                feature_names.remove(name)
            

        # 对每个特征计算统计量
        for feature_name in feature_names:
            values = []
            for features in features_list:
                value = features.get(feature_name)
                if isinstance(value, (int, float)):
                    values.append(value)


            num = len(values)
            if num == 0:
                continue
            average = np.mean(values)
            std_dev = np.std(values)
            median = np.median(values)
            min_value = np.min(values)
            max_value = np.max(values)

            row_position = table.rowCount()
            table.insertRow(row_position)

            # Feature
            feature_item = QtWidgets.QTableWidgetItem(str(feature_name))
            table.setItem(row_position, 0, feature_item)

            # Num
            num_item = QtWidgets.QTableWidgetItem(str(num))
            table.setItem(row_position, 1, num_item)

            # Average
            average_item = QtWidgets.QTableWidgetItem(f"{average:.4f}")
            table.setItem(row_position, 2, average_item)

            # Std Dev
            std_dev_item = QtWidgets.QTableWidgetItem(f"{std_dev:.4f}")
            table.setItem(row_position, 3, std_dev_item)

            # Median
            median_item = QtWidgets.QTableWidgetItem(f"{median:.4f}")
            table.setItem(row_position, 4, median_item)

            # Min
            min_item = QtWidgets.QTableWidgetItem(f"{min_value:.4f}")
            table.setItem(row_position, 5, min_item)

            # Max
            max_item = QtWidgets.QTableWidgetItem(f"{max_value:.4f}")
            table.setItem(row_position, 6, max_item)