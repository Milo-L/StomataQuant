"""Stable-ID Qt rows. Sorting may move cells; Python never caches row numbers."""
import weakref
from numbers import Integral
from PyQt5 import QtCore, QtWidgets, sip
from shape_history import shape_identity
from measurements import finite_numeric

KINDS = ('polygon', 'rotated_rectangle', 'rectangle', 'line', 'point')
ID_ROLE = QtCore.Qt.UserRole + 1
EXPORT_ROLE = QtCore.Qt.UserRole + 2


def set_exact_data(item, role, value):
    # QVariant equality may treat nearby doubles as equal. Clear the old value
    # first so sub-display-precision edits still replace the exported measurement.
    if item.data(role) != value:
        item.setData(role, None)
        item.setData(role, value)


class MeasurementTable(QtWidgets.QTableWidget):
    selectionSettled = QtCore.pyqtSignal()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._selection_interacting = False
        self._selection_pending = False
        self.selection_modifiers = None
        self._selection_anchor = QtCore.QPersistentModelIndex()
        self.itemSelectionChanged.connect(self._selection_changed)
        self.currentItemChanged.connect(self._selection_changed)

    def _selection_changed(self, *args):
        if self._selection_interacting:
            self._selection_pending = True

    def _finish_selection(self, modifiers):
        self._selection_interacting = False
        if self._selection_pending:
            self._selection_pending = False
            self.selection_modifiers = modifiers
            try:
                self.selectionSettled.emit()
            finally:
                self.selection_modifiers = None

    def mousePressEvent(self, event):
        # Qt updates selection before currentIndex. Publish once, after the
        # complete gesture, without resetting the originating view's anchor.
        self._selection_interacting = True
        self._selection_pending = (event.button() == QtCore.Qt.LeftButton
                                   and self.indexAt(event.pos()).isValid())
        self._pointer_modifiers = event.modifiers()
        self._shift_base_selection = self.selectionModel().selection()
        index = self.indexAt(event.pos())
        if event.button() == QtCore.Qt.LeftButton and not event.modifiers() & QtCore.Qt.ShiftModifier:
            self._selection_anchor = QtCore.QPersistentModelIndex(index)
        super().mousePressEvent(event)
        if (event.button() == QtCore.Qt.LeftButton and event.modifiers() == QtCore.Qt.NoModifier
                and self.selectionBehavior() == self.SelectRows and not index.isValid()):
            self.clearSelection()
            self.setCurrentItem(None, QtCore.QItemSelectionModel.NoUpdate)
            # An empty type table may have no local selection to change, while
            # other result tables and the Canvas still hold the Select All set.
            self._selection_pending = True
        if event.button() == QtCore.Qt.LeftButton:
            self._apply_shift_range(index, event.modifiers())

    def mouseReleaseEvent(self, event):
        try:
            super().mouseReleaseEvent(event)
        finally:
            self._finish_selection(getattr(self, '_pointer_modifiers', event.modifiers()))

    def mouseDoubleClickEvent(self, event):
        self._selection_interacting = True
        try:
            super().mouseDoubleClickEvent(event)
        finally:
            self._finish_selection(event.modifiers())

    def keyPressEvent(self, event):
        self._selection_interacting = True
        self._selection_pending = False
        self._shift_base_selection = self.selectionModel().selection()
        try:
            super().keyPressEvent(event)
            if event.key() in (QtCore.Qt.Key_Up, QtCore.Qt.Key_Down, QtCore.Qt.Key_Home,
                               QtCore.Qt.Key_End, QtCore.Qt.Key_PageUp, QtCore.Qt.Key_PageDown):
                self._apply_shift_range(self.currentIndex(), event.modifiers())
                if not event.modifiers() & QtCore.Qt.ShiftModifier:
                    self._selection_anchor = QtCore.QPersistentModelIndex(self.currentIndex())
        finally:
            self._finish_selection(event.modifiers())

    def set_selection_primary(self, item, reset_anchor=True):
        self.setCurrentItem(item, QtCore.QItemSelectionModel.NoUpdate)
        # NoUpdate preserves selection but does not reset Qt's private Shift
        # anchor. Use a persistent model index, which follows sorting/deletion.
        if item is None or reset_anchor or not self._selection_anchor.isValid():
            self._selection_anchor = QtCore.QPersistentModelIndex(self.currentIndex())

    def _apply_shift_range(self, index, modifiers):
        if (self.selectionMode() != self.ExtendedSelection or not modifiers & QtCore.Qt.ShiftModifier
                or not index.isValid()):
            return
        anchor = self._selection_anchor
        first = anchor.row() if anchor.isValid() else index.row()
        first, last = sorted((first, index.row()))
        selection = QtCore.QItemSelection(self.model().index(first, 0),
                                         self.model().index(last, self.columnCount()-1))
        model = self.selectionModel()
        if modifiers & QtCore.Qt.ControlModifier:
            model.select(self._shift_base_selection, QtCore.QItemSelectionModel.ClearAndSelect)
            model.select(selection, QtCore.QItemSelectionModel.Select | QtCore.QItemSelectionModel.Rows)
        else:
            model.select(selection, QtCore.QItemSelectionModel.ClearAndSelect | QtCore.QItemSelectionModel.Rows)

    def focusInEvent(self, event):
        self._gaining_focus = True
        try:
            super().focusInEvent(event)
        finally:
            self._gaining_focus = False

    def selectionCommand(self, index, event=None):
        if getattr(self, '_gaining_focus', False):
            return QtCore.QItemSelectionModel.NoUpdate
        return super().selectionCommand(index, event)


def configure_shape_selection(table):
    table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
    table.setSelectionMode(QtWidgets.QAbstractItemView.ExtendedSelection)
    header = table.verticalHeader()
    height = max(24, header.defaultSectionSize())
    header.setSectionResizeMode(QtWidgets.QHeaderView.Fixed)
    header.setMinimumSectionSize(height)
    header.setMaximumSectionSize(height)
    header.setDefaultSectionSize(height)
    table.setWordWrap(False)


HEADERS = {
    'polygon': ['Label', 'Group ID', 'Area ({u}²)', 'Perimeter ({u})',
                'MER Length ({u})', 'MER Width ({u})', 'Circularity', 'Eccentricity',
                'ACH', 'PCH', 'Roundness', 'Convexity', 'Solidity', 'Center Point'],
    'rotated_rectangle': ['Label', 'Group ID', 'Width ({u})', 'Length ({u})',
                          'Aspect Ratio', 'Angle', 'Center Point'],
    'rectangle': ['Label', 'Group ID', 'Width ({u})', 'Length ({u})', 'Aspect Ratio', 'Center Point'],
    'line': ['Label', 'Group ID', 'Length ({u})', 'StartPoint', 'EndPoint', 'Angle', 'Center Point'],
    'point': ['Label', 'Group ID', 'X', 'Y'],
}


def write_cells(table, cells, values, numeric_columns=(), raw_values=None):
    """Hold every item before changing a sort key. Qt relocates the entire row."""
    from dock_widgets import NumericTableWidgetItem
    if cells is None:
        cells = [NumericTableWidgetItem() if i in numeric_columns else QtWidgets.QTableWidgetItem()
                 for i in range(len(values))]
        row = table.rowCount()
        table.insertRow(row)
        sort_column = table.horizontalHeader().sortIndicatorSection()
        order = [i for i in range(len(cells)) if i != sort_column]
        if 0 <= sort_column < len(cells):
            order.append(sort_column)
        for column, value in enumerate(values):
            cells[column].setText(value)
        for column in order:
            table.setItem(row, column, cells[column])
    else:
        for item, value in zip(cells, values):
            if item.text() != value:
                item.setText(value)
    if raw_values is not None:
        for item, value in zip(cells, raw_values):
            raw = (int(value) if isinstance(value, Integral) else float(value)) if finite_numeric(value) else value
            set_exact_data(item, EXPORT_ROLE, raw)
    return cells


class MeasurementRows:
    def _init_measurement_rows(self):
        self._rows = {}
        self._result_states = {}
        self._result_shapes = weakref.WeakValueDictionary()
        self._canvas_ref = lambda: None
        self._selecting = False
        self._primary_id = None
        self._header_units = {}
        for kind in KINDS:
            table = getattr(self, kind + '_table')
            table.setColumnCount(len(HEADERS[kind]) + 2)
            table.setHorizontalHeaderLabels([h.format(u='pixel') for h in HEADERS[kind]]
                                            + ['Measurement Status', 'Measurement Error'])
            table.itemSelectionChanged.connect(lambda t=table: self._measurement_selected(t))
            table.selectionSettled.connect(lambda t=table: self._measurement_selected(t))

    def bind_canvas(self, canvas):
        if self._canvas_ref() is canvas:
            return
        # Keep completed Qt projections per Canvas, so navigation does not rebuild
        # thousands of measured rows after eager batch updates.
        if hasattr(self, 'tab_widget'):
            fields = ('tab_widget', '_rows', '_result_states', '_result_shapes', '_header_units', '_primary_id')
            fields += tuple(kind + '_table' for kind in KINDS)
            if not hasattr(self, '_projections'):
                self._projections = weakref.WeakKeyDictionary()
            previous = self._canvas_ref()
            if previous is not None:
                self._projections[previous] = {name: getattr(self, name) for name in fields}
            bundle = self._projections.get(canvas) if canvas is not None else None
            self.tab_widget.hide()
            self.tab_widget.setParent(self)
            if bundle is not None:
                for name, value in bundle.items():
                    setattr(self, name, value)
            else:
                old = self.tab_widget
                self.tab_widget = QtWidgets.QTabWidget(self)
                for kind in KINDS:
                    table = MeasurementTable()
                    setattr(self, kind + '_table', table)
                    self.tab_widget.addTab(table, kind.replace('_', ' ').title())
                    self.setup_table(table)
                self._init_measurement_rows()
                if previous is None:
                    old.deleteLater()
            self.setWidget(self.tab_widget)
        else:
            self.clear_tables()
        self._canvas_ref = weakref.ref(canvas) if canvas is not None else lambda: None

    def release_projection(self, canvas):
        bundle = getattr(self, '_projections', {}).pop(canvas, None)
        if bundle is not None and bundle['tab_widget'] is not self.tab_widget:
            bundle['tab_widget'].deleteLater()

    def clear_tables(self):
        if not hasattr(self, '_rows'):
            return
        self._selecting = True
        try:
            self._rows.clear()
            self._result_states.clear()
            self._result_shapes.clear()
            self._primary_id = None
            self._header_units.clear()
            for kind in KINDS:
                table = getattr(self, kind + '_table')
                blocker = QtCore.QSignalBlocker(table)
                table.setRowCount(0)
                del blocker
        finally:
            self._selecting = False

    def remove_result(self, uid):
        record = self._rows.pop(uid, None)
        self._result_shapes.pop(uid, None)
        self._result_states.pop(uid, None)
        if self._primary_id == uid:
            self._primary_id = None
        if record:
            kind, cells = record
            table = getattr(self, kind + '_table')
            blocker = QtCore.QSignalBlocker(table)
            table.removeRow(cells[0].row())
            del blocker

    def update_result(self, shape):
        uid, kind = shape_identity(shape), shape.shape_type
        canvas = self._canvas_ref()
        if canvas is not None and canvas._shape_by_id.get(uid) is not shape:
            return
        record = self._rows.get(uid)
        if record and record[0] != kind:
            self.remove_result(uid)
            record = None
        table = getattr(self, kind + '_table')
        unit = getattr(shape, 'unit', 'pixel')
        if self._header_units.get(kind) != unit:
            table.setHorizontalHeaderLabels([h.format(u=unit) for h in HEADERS[kind]]
                                            + ['Measurement Status', 'Measurement Error'])
            self._header_units[kind] = unit
        error = getattr(shape, 'measurement_error', None)
        values = list(shape.feature_results.values()) if shape.feature_results else [shape.label, shape.group_id]
        values = values + ['NA'] * (len(HEADERS[kind]) - len(values))
        values += ['Failed' if error or not shape.feature_results else 'OK', error or
                   ('No measurement result' if not shape.feature_results else '')]
        text = [f'{v:.4f}' if finite_numeric(v) else str(v) for v in values]
        blocker = QtCore.QSignalBlocker(table)
        numeric_columns = {'polygon': range(1, 13), 'point': range(1, 4),
                           'rectangle': range(1, 5), 'line': (1, 2, 5),
                           'rotated_rectangle': range(1, 6)}[kind]
        cells = write_cells(table, record[1] if record else None, text, numeric_columns, values)
        for item, value in zip(cells, values):
            numeric = float(value) if finite_numeric(value) else None
            if item.data(QtCore.Qt.UserRole) != numeric:
                set_exact_data(item, QtCore.Qt.UserRole, numeric)
        cells[0].setData(ID_ROLE, uid)
        self._rows[uid] = kind, cells
        self._result_shapes[uid] = shape
        self._result_states[uid] = (unit, dict(shape.feature_results), shape.label, shape.group_id, error)
        del blocker

    def shape_for_item(self, item):
        if item is None or sip.isdeleted(item):
            return None
        uid = item.data(ID_ROLE)
        shape = self._result_shapes.get(uid)
        canvas = self._canvas_ref()
        if canvas is not None and (sip.isdeleted(canvas) or canvas._shape_by_id.get(uid) is not shape):
            return None
        return shape

    def _measurement_selected(self, table):
        if self._selecting or table._selection_interacting:
            return
        # The type tabs are projections of one collection: an ordinary click
        # replaces the entire selection, while Ctrl preserves other type tabs.
        modifiers = table.selection_modifiers
        if modifiers is not None and not modifiers & QtCore.Qt.ControlModifier:
            self._selecting = True
            try:
                for kind in KINDS:
                    other = getattr(self, kind + '_table')
                    if other is not table:
                        other.clearSelection()
            finally:
                self._selecting = False
        shapes = []
        for kind in KINDS:
            target = getattr(self, kind + '_table')
            for index in target.selectionModel().selectedRows():
                shape = self.shape_for_item(target.item(index.row(), 0))
                if shape is not None:
                    shapes.append(shape)
        primary = self.shape_for_item(table.item(table.currentRow(), 0))
        if primary is None or (modifiers is None and not any(s is primary for s in shapes)):
            primary = shapes[-1] if shapes else None
        self._primary_id = shape_identity(primary) if primary is not None else None
        self.shapeSelectionChanged.emit(shapes)

    def primary_shape(self):
        record = self._rows.get(self._primary_id)
        return self.shape_for_item(record[1][0]) if record else None

    def select_shapes(self, shapes, primary=None, scroll=False):
        shapes = list(shapes)
        if primary is None:
            current = self.primary_shape()
            primary = current if any(s is current for s in shapes) else (shapes[-1] if shapes else None)
        self._primary_id = shape_identity(primary) if primary is not None else None
        self._selecting = True
        try:
            blockers = [QtCore.QSignalBlocker(getattr(self, k + '_table')) for k in KINDS]
            for kind in KINDS:
                getattr(self, kind + '_table').clearSelection()
            for shape in shapes:
                record = self._rows.get(shape_identity(shape))
                if record:
                    kind, cells = record
                    table = getattr(self, kind + '_table')
                    table.selectionModel().select(table.model().index(cells[0].row(), 0),
                        QtCore.QItemSelectionModel.Select | QtCore.QItemSelectionModel.Rows)
            record = self._rows.get(self._primary_id)
            if record:
                kind, cells = record
                table = getattr(self, kind + '_table')
                table.set_selection_primary(cells[0], reset_anchor=scroll)
                self.tab_widget.setCurrentWidget(table)
                if scroll:
                    table.scrollToItem(cells[0], QtWidgets.QAbstractItemView.PositionAtTop)
            elif not shapes:
                for kind in KINDS:
                    getattr(self, kind + '_table').set_selection_primary(None)
            del blockers
        finally:
            self._selecting = False

    def sync_results(self, shapes, *, validated=False):
        """Compatibility/full reconciliation only; ordinary edits use update_result."""
        from measurements import ensure_features
        shapes = list(shapes)
        wanted = {shape_identity(s) for s in shapes}
        for uid in set(self._rows) - wanted:
            self.remove_result(uid)
        for shape in shapes:
            if not validated and shape.visible:
                try:
                    ensure_features(shape, getattr(shape, '_measurement_scale', None))
                    shape.measurement_error = None
                except Exception as error:
                    shape.feature_results = {}
                    shape.measurement_error = str(error)
            state = (shape.unit, dict(shape.feature_results), shape.label, shape.group_id,
                     getattr(shape, 'measurement_error', None))
            if self._result_states.get(shape_identity(shape)) != state:
                self.update_result(shape)

    def populate(self, shapes, *, validated=False):
        self.clear_tables()
        self.sync_results(shapes, validated=validated)

    def update_labels(self, shapes):
        for shape in shapes:
            record = self._rows.get(shape_identity(shape))
            if record:
                record[1][0].setText(str(shape.label))
