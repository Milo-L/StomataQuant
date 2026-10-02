from measurement_rows import MeasurementRows, MeasurementTable, configure_shape_selection, EXPORT_ROLE
from shape_history import shape_identity
# dock_widgets.py
import numpy as np
import csv
from measurements import ensure_features, refresh_shapes, resolve_scale, finite_numeric
from PyQt5 import QtCore, QtGui, QtWidgets
from PyQt5.QtCore import Qt
from functools import wraps
from contextlib import contextmanager
import weakref


@contextmanager
def metadata_table_update(table):
    """Update existing items without recursive edits or intermediate sorting."""
    blocked = table.blockSignals(True)
    sorting = table.isSortingEnabled()
    updates = table.updatesEnabled()
    scroll = (table.horizontalScrollBar().value(), table.verticalScrollBar().value())
    table.setUpdatesEnabled(False)
    table.setSortingEnabled(False)
    try:
        yield
    finally:
        table.setSortingEnabled(sorting)
        table.horizontalScrollBar().setValue(scroll[0])
        table.verticalScrollBar().setValue(scroll[1])
        table.setUpdatesEnabled(updates)
        table.blockSignals(blocked)


class MetadataTable(MeasurementTable):
    def focusInEvent(self, event):
        self._gaining_focus = True
        try:
            super().focusInEvent(event)
        finally:
            self._gaining_focus = False

    def selectionCommand(self, index, event=None):
        # Gaining focus must not toggle a row in MultiSelection mode.
        # Qt can ask for this command with a null event during focusInEvent.
        if getattr(self, '_gaining_focus', False):
            return QtCore.QItemSelectionModel.NoUpdate
        # A double click starts with a press: retain the batch selection when
        # entering an already selected editable cell. Ctrl-click still toggles.
        if (self.selectionMode() != QtWidgets.QAbstractItemView.ExtendedSelection
                and event is not None and event.type() == QtCore.QEvent.MouseButtonPress
                and event.button() == Qt.LeftButton and event.modifiers() == Qt.NoModifier
                and index.flags() & Qt.ItemIsEditable
                and self.selectionModel().isSelected(index)):
            return QtCore.QItemSelectionModel.NoUpdate
        return super().selectionCommand(index, event)


class MetadataDelegate(QtWidgets.QStyledItemDelegate):
    """Capture real targets before sorting; commit only validated editor data."""
    def __init__(self, dock):
        super().__init__(dock.table_widget)
        self.dock = dock

    def createEditor(self, parent, option, index):
        editor = QtWidgets.QLineEdit(parent)
        editor.targets, editor.field = self.dock.edit_targets(index)
        editor.history_epochs = [getattr(shape, '_history_epoch', 0) for shape in editor.targets]
        if editor.field == 'classnum':
            editor.setValidator(QtGui.QRegularExpressionValidator(
                QtCore.QRegularExpression('[0-9]+'), editor))
        return editor

    def setEditorData(self, editor, index):
        editor.setText(str(index.data(Qt.EditRole) or ''))
        editor.selectAll()

    def setModelData(self, editor, model, index):
        if (editor.hasAcceptableInput() and editor.history_epochs ==
                [getattr(shape, '_history_epoch', 0) for shape in editor.targets]):
            # The receiver is queued so a LabelList merge cannot delete the
            # active editor's row during QAbstractItemView.commitData().
            self.dock.metadataEdited.emit(editor.targets, editor.field, editor.text())

    def eventFilter(self, editor, event):
        if (event.type() == QtCore.QEvent.KeyPress
                and event.key() in (Qt.Key_Return, Qt.Key_Enter)
                and not editor.hasAcceptableInput()):
            QtWidgets.QToolTip.showText(editor.mapToGlobal(editor.rect().bottomLeft()),
                                       'Classnum must be a non-negative integer.', editor)
            return True
        return super().eventFilter(editor, event)


def write_measurement_table(table, path, parent):
    from io import StringIO
    from safe_io import write_text_atomic
    view = parent.get_current_graphics_view() if hasattr(parent, 'get_current_graphics_view') else None
    scale = resolve_scale(parent, view) or {}
    metadata = [scale.get('unit', 'pixel'), scale.get('scale', 1.), 'pixel']
    with StringIO(newline='') as file:
        writer = csv.writer(file)
        writer.writerow([table.horizontalHeaderItem(c).text() for c in range(table.columnCount())]
                        + (['Density Unit', 'Image Area Unit'] if table.property('density_unit') else [])
                        + ['Measurement Unit', 'Scale (unit/pixel)', 'Coordinate Unit'])
        for row in range(table.rowCount()):
            writer.writerow([(table.item(row, c).data(EXPORT_ROLE)
                              if table.item(row, c).data(EXPORT_ROLE) is not None
                              else table.item(row, c).text()) if table.item(row, c) else ''
                             for c in range(table.columnCount())]
                            + ([table.property('density_unit'), table.property('image_area_unit')]
                               if table.property('density_unit') else []) + metadata)
        write_text_atomic(path, file.getvalue())


def stable_table_rows(*attributes):
    """Suspend sorting for a whole write, preserving the user's sort settings."""
    def decorate(method):
        @wraps(method)
        def wrapped(self, *args, **kwargs):
            tables = [getattr(self, name) for name in attributes] if attributes else [args[0]]
            states = [(table, table.isSortingEnabled(),
                       table.horizontalHeader().sortIndicatorSection(),
                       table.horizontalHeader().sortIndicatorOrder()) for table in tables]
            try:
                for table in tables:
                    table.setSortingEnabled(False)
                return method(self, *args, **kwargs)
            finally:
                for table, enabled, column, order in states:
                    table.horizontalHeader().setSortIndicator(column, order)
                    table.setSortingEnabled(enabled)
        return wrapped
    return decorate

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
    pointClassChanged = QtCore.pyqtSignal(object, object)
    metadataEdited = QtCore.pyqtSignal(list, str, str)
    # 添加两个信号，用于通知可见性和选择状态的改变
    # 定义一个信号，用于通知可见性改变
    visibilityChanged = QtCore.pyqtSignal() 
     # 定义一个信号，用于通知选择状态改变，传递一个形状列表
    selectionClickedinShapeList = QtCore.pyqtSignal(list)

    def __init__(self, parent=None):
        super().__init__("ShapeList", parent)
        # 创建一个 QTableWidget，设置列数为 4，并设置列标题。
        self.table_widget = MetadataTable()
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
        configure_shape_selection(self.table_widget)
        self.table_widget.setEditTriggers(QtWidgets.QAbstractItemView.DoubleClicked |
                                          QtWidgets.QAbstractItemView.EditKeyPressed)
        self.table_widget.setItemDelegate(MetadataDelegate(self))
        self.table_widget.setToolTip('Click selects one row; Ctrl-click toggles; Shift-click selects a range. Double-click to edit one shape; F2 edits selected shapes. Enter confirms; Esc cancels.')
            
        self.table_widget.itemSelectionChanged.connect(self.on_shapelist_item_selected)
        self.table_widget.selectionSettled.connect(self.on_shapelist_item_selected)
        self.table_widget.itemChanged.connect(self.on_metadata_changed)
        self.table_widget.setContextMenuPolicy(Qt.CustomContextMenu)
        self.table_widget.customContextMenuRequested.connect(self.create_context_menu)
        # self.table_widget.itemChanged.connect(self.on_item_changed)  # 连接 itemChanged 信号

    
    def create_context_menu(self, position):
        menu = QtWidgets.QMenu(self)
        actions = {menu.addAction(name): callback for name, callback in (
            ('Select All', self.table_widget.selectAll),
            ('Delete Selected', self.parent().delete_selected_shape),
            ('Export Annotation', self.export_selected_annotation))}
        action = menu.exec_(self.table_widget.viewport().mapToGlobal(position))
        if action in actions:
            actions[action]()

    def export_selected_annotation(self):
        from selected_annotations import serialize_selected
        from safe_io import write_text_atomic
        from measurements import measurement_key
        parent = self.parent()
        view = parent.get_current_graphics_view()
        if not view or not view.canvas:
            return
        canvas = view.canvas
        shapes = [self.table_widget.item(index.row(), 1).data(Qt.UserRole)
                  for index in self.table_widget.selectionModel().selectedRows()]
        try:
            kind, data = serialize_selected(canvas, shapes)
            snapshots = [measurement_key(shape, None) for shape in shapes]
            path, _ = QtWidgets.QFileDialog.getSaveFileName(parent, 'Export selected ' + kind + ' annotations', '', 'Annotations (*.txt)')
            if not path:
                return
            if (parent.get_current_graphics_view() is not view or
                    snapshots != [measurement_key(shape, None) for shape in shapes] or
                    any(not any(item is shape for item in canvas.shapes) for shape in shapes)):
                raise ValueError('Selection or annotations changed during export. Please retry.')
            write_text_atomic(path, data)
        except Exception as error:
            QtWidgets.QMessageBox.warning(parent, 'Annotation export', str(error))

    def clearSelection(self):
        self.table_widget.clearSelection()

    def findItemByShape(self, shape):
        item = getattr(self, '_items_by_id', {}).get(shape_identity(shape))
        return item.row() if item is not None else -1

    def selectItem(self, row):
        self.selectItems([row])
    
    def selectItems(self, rows, reset_anchor=True, primary_item=None):
        table = self.table_widget
        selection_model = table.selectionModel()
        selection = QtCore.QItemSelection()
        primary = None
        for row in rows:
            if 0 <= row < table.rowCount():
                primary = table.item(row, 1)
                index = table.model().index(row, 1)
                selection.select(index, index)
        table.set_selection_primary(primary_item if primary_item is not None else primary, reset_anchor)
        selection_model.select(selection, QtCore.QItemSelectionModel.ClearAndSelect | QtCore.QItemSelectionModel.Rows)

    def primary_shape(self):
        table = self.table_widget
        item = table.item(table.currentRow(), 1)
        return item.data(Qt.UserRole) if item is not None else None

    def select_shapes(self, shapes, primary=None, scroll=False):
        table = self.table_widget
        blocker = QtCore.QSignalBlocker(table)
        item = getattr(self, '_items_by_id', {}).get(shape_identity(primary)) if primary is not None else None
        self.selectItems([self.findItemByShape(s) for s in shapes], reset_anchor=scroll, primary_item=item)
        if item is not None and scroll:
            table.scrollToItem(item, QtWidgets.QAbstractItemView.PositionAtTop)
        del blocker
    
    def scrollToItem(self, row):
        item = self.table_widget.item(row, 1)
        if item is not None:
            self.table_widget.scrollToItem(item, QtWidgets.QAbstractItemView.PositionAtTop)

    def populate(self, shapes):
        self.shapes = shapes
        self._items_by_id = {}
        self._row_states = {}
        with metadata_table_update(self.table_widget):
            self.table_widget.setRowCount(0)
            self.table_widget.setRowCount(len(shapes))
            for row, shape in enumerate(shapes):
                self._append_row(shape, row)

    @staticmethod
    def _row_state(shape):
        return (shape.label or '', shape.group_id, shape.classnum, shape.shape_type, shape.visible)

    def _append_row(self, shape, row=None):
        table = self.table_widget
        if row is None:
            row = table.rowCount()
            table.setRowCount(row + 1)
        if not hasattr(self, '_items_by_id'):
            self._items_by_id, self._row_states = {}, {}
        checkbox = QtWidgets.QCheckBox()
        checkbox.setChecked(shape.visible)
        checkbox.stateChanged.connect(lambda state, ref=weakref.ref(shape):
                                      self.on_visibility_changed(state, ref()) if ref() is not None else None)
        table.setCellWidget(row, 0, checkbox)
        values = self._row_state(shape)[:4]
        color = shape.get_color_by_classnum(shape.classnum)
        for column, value in enumerate(values, 1):
            cls = NumericTableWidgetItem if column in (2, 3) else QtWidgets.QTableWidgetItem
            item = cls(str(value))
            item.setData(Qt.UserRole, shape)
            item.setTextAlignment(Qt.AlignCenter)
            item.setForeground(color)
            flags = Qt.ItemIsEnabled | Qt.ItemIsSelectable
            if column in (1, 3):
                flags |= Qt.ItemIsEditable
            item.setFlags(flags)
            table.setItem(row, column, item)
            if column == 1:
                self._items_by_id[shape_identity(shape)] = item
        self._row_states[shape_identity(shape)] = self._row_state(shape)

    def sync_shapes(self, shapes):
        """Keep existing items/selection on local edits; rebuild once for replaced objects."""
        desired = {shape_identity(s): s for s in shapes}
        existing = getattr(self, '_items_by_id', {})
        removed = set(existing) - set(desired)
        added = [s for s in shapes if shape_identity(s) not in existing]
        if not existing or len(removed) > len(existing) // 2:
            self.populate(shapes)
            return
        table = self.table_widget
        self.shapes = shapes
        if removed or added:
            with metadata_table_update(table):
                for row, identity in sorted(((existing[i].row(), i) for i in removed), reverse=True):
                    table.removeRow(row)
                    del existing[identity]
                    self._row_states.pop(identity, None)
                start = table.rowCount()
                table.setRowCount(start + len(added))
                for row, shape in enumerate(added, start):
                    self._append_row(shape, row)
        changed = [s for s in shapes if self._row_states.get(shape_identity(s)) != self._row_state(s)]
        if changed:
            self.update_metadata(changed)

    def edit_targets(self, index):
        shape = index.data(Qt.UserRole)
        selected = [self.table_widget.item(i.row(), 1).data(Qt.UserRole)
                    for i in self.table_widget.selectionModel().selectedRows()]
        targets = selected if any(s is shape for s in selected) else [shape]
        return targets, 'label' if index.column() == 1 else 'classnum'

    def on_metadata_changed(self, item):
        if item.column() not in (1, 3):
            return
        shape = item.data(Qt.UserRole)
        if shape is None:
            return
        field = 'label' if item.column() == 1 else 'classnum'
        old = (shape.label or '') if field == 'label' else str(shape.classnum)
        text = item.text()
        if text == old:
            return
        targets, _ = self.edit_targets(self.table_widget.indexFromItem(item))
        blocker = QtCore.QSignalBlocker(self.table_widget)
        item.setText(old)
        del blocker
        if field == 'classnum':
            from point_annotations import class_id
            try:
                class_id(text)
            except ValueError as error:
                QtWidgets.QMessageBox.warning(self, 'Invalid class ID', str(error))
                return
        self.metadataEdited.emit(targets, field, text)

    def update_metadata(self, shapes):
        table = self.table_widget
        with metadata_table_update(table):
            for shape in shapes:
                row = self.findItemByShape(shape)
                if row < 0:
                    continue
                state = self._row_state(shape)
                color = shape.get_color_by_classnum(shape.classnum)
                for column, value in enumerate(state[:4], 1):
                    item = table.item(row, column)
                    if item.text() != str(value):
                        item.setText(str(value))
                    item.setForeground(color)
                checkbox = table.cellWidget(row, 0)
                blocker = QtCore.QSignalBlocker(checkbox)
                checkbox.setChecked(shape.visible)
                del blocker
                self._row_states[shape_identity(shape)] = state

    # def on_item_changed(self, item):
    #     if item.column() == 1:  # Label 列
    #         shape = item.data(QtCore.Qt.UserRole)
    #         new_label = item.text()
    #         shape.label = new_label
    #         print(f"Shape label updated to: {new_label}")

# 当勾选可见性一列时，
# 更新形状的可见性状态。发射 visibilityChanged 信号。
    def on_visibility_changed(self, state, shape):
        visible = state == QtCore.Qt.Checked
        if shape.visible == visible:
            return
        parent = self.parent()
        view = parent.get_current_graphics_view() if parent is not None else None
        canvas = view.canvas if view is not None else None
        if canvas is None or not any(item is shape for item in canvas.shapes):
            return
        canvas.save_state()
        shape.visible = visible
        canvas.shapesChanged.emit()
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
        if (self.table_widget._selection_interacting
                or getattr(parent, '_syncing_shape_selection', False)):
            return
        if getattr(parent, '_noCanvasSelectionSlot', False):
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
        for row in range(self.table_widget.rowCount()):
            shape = self.table_widget.item(row, 1).data(Qt.UserRole)
            checkbox = self.table_widget.cellWidget(row, 0)
            if checkbox:
                blocker = QtCore.QSignalBlocker(checkbox)
                checkbox.setChecked(shape.visible)
                del blocker
        self.table_widget.viewport().update()

    def add_shape(self, shape):
        with metadata_table_update(self.table_widget):
            self._append_row(shape)
        if not any(s is shape for s in self.shapes):
            self.shapes.append(shape)


class LabelListDock(QtWidgets.QDockWidget):
    visibilityChanged = QtCore.pyqtSignal(str, bool)
    metadataEdited = QtCore.pyqtSignal(list, str, str)

    def __init__(self, parent=None):
        super().__init__('LabelList', parent)
        self.table_widget = MetadataTable()
        self.table_widget.setColumnCount(2)
        self.table_widget.setHorizontalHeaderLabels(['Visible', 'Label'])
        self.table_widget.horizontalHeader().setStretchLastSection(True)
        self.table_widget.setSortingEnabled(True)
        self.table_widget.setEditTriggers(QtWidgets.QAbstractItemView.DoubleClicked |
                                          QtWidgets.QAbstractItemView.EditKeyPressed)
        self.table_widget.setItemDelegate(MetadataDelegate(self))
        self.table_widget.itemChanged.connect(self.on_label_changed)
        self.table_widget.setToolTip('Double-click a label to rename it for all shapes in the current image.')
        self.setWidget(self.table_widget)
        self.labels = []
        self.shapes = []
        self.checkbox_dict = {}

    def edit_targets(self, index):
        label = index.data(Qt.UserRole)
        return [s for s in self.shapes if s.label == label], 'label'

    def on_label_changed(self, item):
        if item.column() != 1 or item.text() == item.data(Qt.UserRole):
            return
        targets, field = self.edit_targets(self.table_widget.indexFromItem(item))
        text = item.text()
        blocker = QtCore.QSignalBlocker(self.table_widget)
        item.setText(item.data(Qt.UserRole) or '')
        del blocker
        self.metadataEdited.emit(targets, field, text)

    def _append_label(self, label):
        row = self.table_widget.rowCount()
        self.table_widget.insertRow(row)
        item = QtWidgets.QTableWidgetItem(label)
        item.setData(Qt.UserRole, label)
        self.table_widget.setItem(row, 1, item)
        checkbox = QtWidgets.QCheckBox()
        checkbox.setProperty('label', label)
        checkbox.setChecked(True)
        checkbox.stateChanged.connect(
            lambda state, box=checkbox: self.on_visibility_changed(state, box.property('label')))
        self.table_widget.setCellWidget(row, 0, checkbox)
        return item

    def populate(self, shapes, get_color_func):
        with metadata_table_update(self.table_widget):
            self.table_widget.setRowCount(0)
            self.checkbox_dict.clear()
        self.sync_labels(shapes, get_color_func)

    def sync_labels(self, shapes, get_color_func, renames=None):
        """Reconcile label rows, keeping unchanged items and checkbox connections."""
        self.shapes = shapes
        groups = {}
        for shape in shapes:
            if shape.label is not None:
                group = groups.setdefault(shape.label, [shape.classnum, False])
                group[1] = group[1] or shape.visible
        table = self.table_widget
        renames = renames or {}
        selected = {renames.get(index.data(Qt.UserRole), index.data(Qt.UserRole))
                    for index in table.selectionModel().selectedIndexes() if index.column() == 1}
        with metadata_table_update(table):
            items = {table.item(row, 1).data(Qt.UserRole): table.item(row, 1)
                     for row in range(table.rowCount())}
            for old, new in renames.items():
                if old in items and old not in groups and new in groups and new not in items:
                    item = items.pop(old)
                    item.setData(Qt.UserRole, new)
                    item.setText(new)
                    table.cellWidget(item.row(), 0).setProperty('label', new)
                    items[new] = item
            for label, item in list(items.items()):
                if label not in groups:
                    table.removeRow(item.row())
                    del items[label]
            for label in sorted(groups):
                category, visible = groups[label]
                item = items.get(label)
                if item is None:
                    item = self._append_label(label)
                item.setForeground(get_color_func(category))
                checkbox = table.cellWidget(item.row(), 0)
                blocker = QtCore.QSignalBlocker(checkbox)
                checkbox.setChecked(visible)
                del blocker
                item.setSelected(label in selected)
            self.labels = list(groups)
            self.checkbox_dict = {label: group[1] for label, group in groups.items()}

    def on_visibility_changed(self, state, label):
        visible = state == Qt.Checked
        self.checkbox_dict[label] = visible
        self.visibilityChanged.emit(label, visible)

    def add_label(self, label):
        if label is None:
            return
        parent = self.parent()
        if hasattr(parent, 'get_current_shapes'):
            self.shapes = parent.get_current_shapes()
        with metadata_table_update(self.table_widget):
            item = next((self.table_widget.item(row, 1)
                         for row in range(self.table_widget.rowCount())
                         if self.table_widget.item(row, 1).data(Qt.UserRole) == label), None)
            created = item is None
            if created:
                item = self._append_label(label)
                self.labels.append(label)
                self.checkbox_dict[label] = True
            shape = next((s for s in reversed(self.shapes) if s.label == label), None)
            if shape is not None:
                if created:
                    item.setForeground(shape.get_color_by_classnum(shape.classnum))
                checkbox = self.table_widget.cellWidget(item.row(), 0)
                blocker = QtCore.QSignalBlocker(checkbox)
                checkbox.setChecked(shape.visible if created else checkbox.isChecked() or shape.visible)
                self.checkbox_dict[label] = checkbox.isChecked()
                del blocker


class MeasuredResultsDock(MeasurementRows, QtWidgets.QDockWidget):
    shapeSelectionChanged = QtCore.pyqtSignal(list)
    def __init__(self, parent=None):
        super().__init__("MeasuredResults(Shapes)", parent)
        self.tab_widget = QtWidgets.QTabWidget()
        self.setWidget(self.tab_widget)

        # 创建用于不同形状的 QTableWidget
        self.polygon_table = MeasurementTable()
        self.rotated_rectangle_table = MeasurementTable()
        self.rectangle_table = MeasurementTable()
        self.line_table = MeasurementTable()
        self.point_table = MeasurementTable()

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
        self._init_measurement_rows()
        #         # 初始化排序状态字典
        # self.sort_order = {}

    def setup_table(self, table):
        table.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        configure_shape_selection(table)
        table.horizontalHeader().setStretchLastSection(False)
        table.horizontalHeader().setSectionResizeMode(QtWidgets.QHeaderView.Interactive)
        # Add context menu
        table.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        table.customContextMenuRequested.connect(lambda pos: self.create_context_menu(table, pos))
        # Add shortcut Ctrl+A
        select_all_shortcut = QtWidgets.QShortcut(QtGui.QKeySequence("Ctrl+A"), table)
        select_all_shortcut.setContext(Qt.WidgetShortcut)
        select_all_shortcut.activated.connect(table.selectAll)
        # Add copy action
        copy_action = QtWidgets.QAction("Copy", table)
        copy_action.setShortcut(QtGui.QKeySequence.Copy)
        copy_action.setShortcutContext(Qt.WidgetShortcut)
        copy_action.setToolTip('Copy (Ctrl+C)')
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
        menu = QtWidgets.QMenu(self)
        actions = {menu.addAction(name): callback for name, callback in (
            ('Select All', table.selectAll),
            ('Copy', lambda: self.copy_selected_rows(table)),
            ('Export CSV', lambda: self.save_table_as(table)))}
        action = menu.exec_(table.viewport().mapToGlobal(position))
        if action in actions:
            actions[action]()

    def copy_selected_rows(self, table):
        from io import StringIO
        rows = sorted({index.row() for index in table.selectedIndexes()})
        if not rows:
            return
        stream = StringIO(newline='')
        writer = csv.writer(stream, delimiter='\t', lineterminator='\r\n')
        writer.writerow([table.horizontalHeaderItem(c).text() for c in range(table.columnCount())])
        for row in rows:
            values = []
            for column in range(table.columnCount()):
                item = table.item(row, column)
                raw = item.data(EXPORT_ROLE) if item else None
                values.append(raw if raw is not None else item.text() if item else '')
            writer.writerow(values)
        QtWidgets.QApplication.clipboard().setText(stream.getvalue())

    def delete_selected_rows(self, table):
        # Derived results cannot delete annotations or statistical rows.
        return

    def toggle_select_all(self, table):
        if isinstance(table, QtWidgets.QTableWidget):
            if table.selectionModel().hasSelection():
                table.clearSelection()
            else:
                table.selectAll()
        else:
            print("Selected widget is not a QTableWidget.--- by toggle_select_all method")

    def save_table_as(self, table):
        parent = self.parent()
        if hasattr(parent, 'measurements_ready_for_export'):
            if not parent.measurements_ready_for_export():
                return
        elif hasattr(parent, 'refresh_measurements'):
            parent.refresh_measurements(force=True)
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
                try:
                    write_measurement_table(table, path, parent)
                except (OSError, ValueError) as error:
                    QtWidgets.QMessageBox.warning(parent, 'Save failed', str(error))
        else:
            print("Selected widget is not a QTableWidget.---by save_table_as method")

    def _populate_result_rows(self, table, shapes):
        wanted = {shape_identity(shape) for shape in shapes}
        for uid, (kind, cells) in list(self._rows.items()):
            if getattr(self, kind + '_table') is table and uid not in wanted:
                self.remove_result(uid)
        for shape in shapes:
            self.update_result(shape)

    @stable_table_rows('polygon_table')
    def populate_polygon_table(self, shapes):
        if not shapes:
            self._populate_result_rows(self.polygon_table, [])
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

        self._populate_result_rows(self.polygon_table, shapes)


    @stable_table_rows('rotated_rectangle_table')
    def populate_rotated_rectangle_table(self, shapes):
        if not shapes:
            self._populate_result_rows(self.rotated_rectangle_table, [])
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

        self._populate_result_rows(self.rotated_rectangle_table, shapes)


    @stable_table_rows('line_table')
    def populate_line_table(self, shapes):
        if not shapes:
            self._populate_result_rows(self.line_table, [])
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

        self._populate_result_rows(self.line_table, shapes)


    @stable_table_rows('rectangle_table')
    def populate_rectangle_table(self, shapes):
        if not shapes:
            self._populate_result_rows(self.rectangle_table, [])
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

        self._populate_result_rows(self.rectangle_table, shapes)


    @stable_table_rows('point_table')
    def populate_point_table(self, shapes):
        if not shapes:
            self._populate_result_rows(self.point_table, [])
            return



        headers = [
            'Label', 'Group ID',
            f'X',
            f'Y'
        ]
        self.point_table.setColumnCount(len(headers))
        self.point_table.setHorizontalHeaderLabels(headers)

        self._populate_result_rows(self.point_table, shapes)


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
        select_all_shortcut.setContext(Qt.WidgetShortcut)
        select_all_shortcut.activated.connect(table.selectAll)
        # Add copy action
        copy_action = QtWidgets.QAction("Copy", table)
        copy_action.setShortcut(QtGui.QKeySequence.Copy)
        copy_action.setShortcutContext(Qt.WidgetShortcut)
        copy_action.setToolTip('Copy (Ctrl+C)')
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
        menu = QtWidgets.QMenu(self)
        actions = {menu.addAction(name): callback for name, callback in (
            ('Select All', table.selectAll),
            ('Copy', lambda: self.copy_selected_rows(table)),
            ('Export CSV', lambda: self.save_table_as(table)))}
        action = menu.exec_(table.viewport().mapToGlobal(position))
        if action in actions:
            actions[action]()

    def copy_selected_rows(self, table):
        from io import StringIO
        rows = sorted({index.row() for index in table.selectedIndexes()})
        if not rows:
            return
        stream = StringIO(newline='')
        writer = csv.writer(stream, delimiter='\t', lineterminator='\r\n')
        writer.writerow([table.horizontalHeaderItem(c).text() for c in range(table.columnCount())])
        for row in rows:
            values = []
            for column in range(table.columnCount()):
                item = table.item(row, column)
                raw = item.data(EXPORT_ROLE) if item else None
                values.append(raw if raw is not None else item.text() if item else '')
            writer.writerow(values)
        QtWidgets.QApplication.clipboard().setText(stream.getvalue())

    def delete_selected_rows(self, table):
        # Derived results cannot delete annotations or statistical rows.
        return

    def toggle_select_all(self, table):
        if isinstance(table, QtWidgets.QTableWidget):
            if table.selectionModel().hasSelection():
                table.clearSelection()
            else:
                table.selectAll()
        else:
            print("Selected widget is not a QTableWidget. --- by toggle_select_all method")

    def save_table_as(self, table):
        parent = self.parent()
        if hasattr(parent, 'measurements_ready_for_export'):
            if not parent.measurements_ready_for_export():
                return
        elif hasattr(parent, 'refresh_measurements'):
            parent.refresh_measurements(force=True)
        controller = getattr(parent, 'measurement_controller', None)
        if controller is not None:
            canvas = controller.active()
            if canvas is not None:
                state = controller.state(canvas)
                controller.summary_rows.write(state.summary, set(state.summary.bins),
                                              set(state.summary.counts), canvas.image_size, state.scale)
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
                try:
                    write_measurement_table(table, path, parent)
                except (OSError, ValueError) as error:
                    QtWidgets.QMessageBox.warning(parent, 'Save failed', str(error))
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

    def populate(self, shapes, image_width, image_height, scale_info=None, *, validated=False):
        if not validated:
            refresh_shapes(shapes, scale_info)
        # 使用形状数据填充表格
        
        self.populate_summary_table(shapes, image_width, image_height, scale_info)

        if any(shape.feature_results for shape in shapes):
            self.populate_feature_tables(shapes)
        else:
            self.populate_feature_tables([])

    @stable_table_rows('summary_table')
    def populate_summary_table(self, shapes, image_width, image_height, scale_info=None):
        self.summary_table.setRowCount(0)  # 清空现有内容


        from measurements import summary_area
        image_area, area_unit = summary_area(QtCore.QSize(image_width, image_height), scale_info)
        density_unit = 'count/' + area_unit
        self.summary_table.setProperty('density_unit', density_unit)
        self.summary_table.setProperty('image_area_unit', area_unit)

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
            for column, value in enumerate([str(label), shape_type, num, density, image_area]):
                self.summary_table.item(row_position, column).setData(EXPORT_ROLE, value)

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

    @stable_table_rows()
    def populate_feature_table(self, table, features_list):
        # 清空表格
        table.setRowCount(0)

        if not features_list:
            return

        # 获取特征名称列表
        feature_names = list(dict.fromkeys(key for features in features_list for key in features))
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
                if finite_numeric(value):
                    values.append(float(value))


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
            for column, value in enumerate([feature_name, num, average, std_dev, median, min_value, max_value]):
                table.item(row_position, column).setData(EXPORT_ROLE, float(value) if finite_numeric(value) else value)
