"""Review and stage per-image calibration without mutating canceled dialogs."""
from PyQt5 import QtCore, QtWidgets, sip
from measurements import apply_scale, resolve_scale, positive_number, validated_scale
from dialog_ui import ResponsiveDialog


class SetMeasuringScaleDialog(ResponsiveDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.main_window = parent
        self.setWindowTitle('Measurement scales — all open images')
        self.resize(820, 620)
        self.tabs = [parent.tabWidget.widget(i) for i in range(parent.tabWidget.count())] if hasattr(parent, 'tabWidget') else []
        self.pending_local = {}
        self.global_changed = False
        self.pending_global = getattr(parent, 'global_scale_info', None)
        self.staged = False
        self.input_dirty = False
        layout = QtWidgets.QVBoxLayout(self)
        self.table = QtWidgets.QTableWidget(len(self.tabs), 4, self)
        self.table.setHorizontalHeaderLabels(['Image / Tab', 'Scale (unit/pixel)', 'Unit', 'Status'])
        self.table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QtWidgets.QAbstractItemView.SingleSelection)
        self.table.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        self.table.horizontalHeader().setSectionResizeMode(0, QtWidgets.QHeaderView.Stretch)
        for column in (1, 2, 3):
            self.table.horizontalHeader().setSectionResizeMode(column, QtWidgets.QHeaderView.ResizeToContents)
        self.table.setMinimumHeight(self.table.verticalHeader().defaultSectionSize() * 3 +
                                    self.table.horizontalHeader().sizeHint().height())
        self.table.setMaximumHeight(self.table.minimumHeight() + 20)
        layout.addWidget(self.table)
        selected_group = QtWidgets.QGroupBox('Selected image scale', self)
        selected_layout = QtWidgets.QVBoxLayout(selected_group)
        self.selected_image_label = QtWidgets.QLabel('Selected image: None')
        selected_layout.addWidget(self.selected_image_label)
        form = QtWidgets.QFormLayout()
        self.pixel_distance_edit = QtWidgets.QLineEdit()
        self.real_distance_edit = QtWidgets.QLineEdit()
        self.unit_combo = QtWidgets.QComboBox()
        self.unit_combo.addItems(['nm', 'μm', 'mm', 'cm', 'm', 'km'])
        self.pixel_distance_label = QtWidgets.QLabel('Pixel distance:')
        self.real_distance_label = QtWidgets.QLabel('Real-world distance:')
        self.unit_label = QtWidgets.QLabel('Unit:')
        for label, control in ((self.pixel_distance_label, self.pixel_distance_edit),
                               (self.real_distance_label, self.real_distance_edit),
                               (self.unit_label, self.unit_combo)):
            label.setBuddy(control)
            form.addRow(label, control)
        selected_layout.addLayout(form)
        self.calculated_scale_label = QtWidgets.QLabel('Calculated scale: —')
        selected_layout.addWidget(self.calculated_scale_label)
        layout.addWidget(selected_group)
        selected_actions = QtWidgets.QGroupBox('Selected image actions', self)
        selected_buttons = QtWidgets.QHBoxLayout(selected_actions)
        self.apply_selected_button = QtWidgets.QPushButton('Set selected image')
        self.clear_selected_button = QtWidgets.QPushButton('Clear selected scale')
        selected_buttons.addWidget(self.apply_selected_button)
        selected_buttons.addWidget(self.clear_selected_button)
        layout.addWidget(selected_actions)
        global_actions = QtWidgets.QGroupBox('Global / all images', self)
        global_layout = QtWidgets.QVBoxLayout(global_actions)
        global_buttons = QtWidgets.QHBoxLayout()
        self.apply_all_button = QtWidgets.QPushButton('Apply to All / Global')
        self.clear_global_button = QtWidgets.QPushButton('Clear global scale')
        global_buttons.addWidget(self.apply_all_button)
        global_buttons.addWidget(self.clear_global_button)
        global_layout.addLayout(global_buttons)
        self.global_checkbox = QtWidgets.QCheckBox('Set global scale for all images')
        global_layout.addWidget(self.global_checkbox)
        layout.addWidget(global_actions)
        layout.addWidget(QtWidgets.QLabel('Changes are applied when you click OK. Cancel keeps all scales unchanged.'))
        box = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel)
        self.ok_button, self.cancel_button = box.button(box.Ok), box.button(box.Cancel)
        box.accepted.connect(self.accept)
        box.rejected.connect(self.reject)
        layout.addWidget(box)
        self.apply_selected_button.clicked.connect(lambda: self.stage(False))
        self.apply_all_button.clicked.connect(lambda: self.stage(True))
        self.clear_selected_button.clicked.connect(self.clear_selected)
        self.clear_global_button.clicked.connect(self.clear_global)
        self.table.itemSelectionChanged.connect(self.load_existing_scale_info)
        self.pixel_distance_edit.textEdited.connect(self.mark_dirty)
        self.real_distance_edit.textEdited.connect(self.mark_dirty)
        self.unit_combo.activated.connect(self.mark_dirty)
        self.pixel_distance_edit.textChanged.connect(self.update_calculated_scale)
        self.real_distance_edit.textChanged.connect(self.update_calculated_scale)
        self.unit_combo.currentTextChanged.connect(self.update_calculated_scale)
        self.global_checkbox.clicked.connect(self.mark_dirty)
        self.redraw()
        if self.tabs:
            self.table.selectRow(max(0, parent.tabWidget.currentIndex()))
        else:
            self.load_existing_scale_info()

    def mark_dirty(self, *args):
        self.input_dirty = True

    def _prepare_dialog(self):
        super()._prepare_dialog()
        # ResponsiveDialog gives every QLabel an ignored width; form labels need
        # their natural width on both Windows and macOS.
        for label in (self.selected_image_label, self.pixel_distance_label,
                      self.real_distance_label, self.unit_label,
                      self.calculated_scale_label):
            label.setWordWrap(False)
            label.setSizePolicy(QtWidgets.QSizePolicy.Preferred,
                                QtWidgets.QSizePolicy.Preferred)

    def update_calculated_scale(self, *args):
        try:
            pixels = positive_number(self.pixel_distance_edit.text())
            real = positive_number(self.real_distance_edit.text())
            scale = validated_scale({'scale': real / pixels})['scale']
        except (ValueError, OverflowError):
            self.calculated_scale_label.setText('Calculated scale: —')
        else:
            self.calculated_scale_label.setText(
                f'Calculated scale: {scale:g} {self.unit_combo.currentText()}/pixel')

    def selected_tab(self):
        row = self.table.currentRow()
        return self.tabs[row] if 0 <= row < len(self.tabs) else None

    def effective(self, tab):
        if tab in self.pending_local:
            return self.pending_local[tab], 'Image override'
        if self.global_changed:
            return self.pending_global or getattr(tab.property('graphics_view'), 'scale_info', None), 'Global' if self.pending_global else 'Image'
        view = tab.property('graphics_view')
        return resolve_scale(self.main_window, view), 'Image' if getattr(view, '_scale_override', False) or not self.pending_global else 'Global'

    def redraw(self):
        for row, tab in enumerate(self.tabs):
            if sip.isdeleted(tab):
                continue
            info, source = self.effective(tab)
            values = [self.main_window.tabWidget.tabText(self.main_window.tabWidget.indexOf(tab)),
                      repr(info['scale']) if info else '—', info['unit'] if info else '—',
                      source if info else 'Not set (count/pixel²)']
            for column, value in enumerate(values):
                item = QtWidgets.QTableWidgetItem(str(value))
                if column == 0:
                    item.setToolTip(tab.property('file_path') or str(value))
                self.table.setItem(row, column, item)

    def load_existing_scale_info(self):
        tab = self.selected_tab()
        self.selected_image_label.setText(
            'Selected image: ' + (self.main_window.tabWidget.tabText(
                self.main_window.tabWidget.indexOf(tab)) if tab is not None else 'None'))
        self.apply_selected_button.setEnabled(tab is not None)
        self.clear_selected_button.setEnabled(tab is not None)
        info = self.effective(tab)[0] if tab else None
        self.pixel_distance_edit.setText('1' if info else '')
        self.real_distance_edit.setText(repr(info['scale']) if info else '')
        if info:
            self.unit_combo.setCurrentText('μm' if info['unit'] in ('um', 'µm') else info['unit'])
        self.global_checkbox.setChecked(False)
        self.input_dirty = False
        self.update_calculated_scale()

    def get_scale_info(self):
        pixels = positive_number(self.pixel_distance_edit.text())
        real = positive_number(self.real_distance_edit.text())
        validated_scale({'scale': real / pixels})
        return pixels, real, self.unit_combo.currentText(), self.global_checkbox.isChecked()

    def stage(self, global_scale):
        try:
            pixels, real, unit, _ = self.get_scale_info()
            info = {'scale': real / pixels, 'unit': unit}
        except (ValueError, OverflowError) as error:
            QtWidgets.QMessageBox.warning(self, 'Invalid scale', str(error))
            return False
        if global_scale:
            self.pending_global, self.global_changed = info, True
            self.pending_local.clear()
        elif self.selected_tab() is not None:
            self.pending_local[self.selected_tab()] = info
        self.staged, self.input_dirty = True, False
        self.redraw()
        return True

    def clear_selected(self):
        tab = self.selected_tab()
        if tab is not None:
            self.pending_local[tab] = None
            self.staged, self.input_dirty = True, False
            self.redraw()
            self.load_existing_scale_info()

    def clear_global(self):
        self.pending_global, self.global_changed = None, True
        self.staged, self.input_dirty = True, False
        self.redraw()

    def accept(self):
        if self.input_dirty or (self.tabs and not self.staged and
                                (self.pixel_distance_edit.text() or self.real_distance_edit.text())):
            if not self.stage(self.global_checkbox.isChecked()):
                return
        if self.global_changed:
            apply_scale(self.main_window, None, self.pending_global, True, refresh=False)
        for tab, info in self.pending_local.items():
            if not sip.isdeleted(tab) and self.main_window.tabWidget.indexOf(tab) >= 0:
                apply_scale(self.main_window, tab.property('graphics_view'), info, False, refresh=False)
        if self.tabs and hasattr(self.main_window, 'measurement_controller'):
            affected = self.tabs if self.global_changed else list(self.pending_local)
            self.main_window.measurement_controller.refresh_tabs(affected)
        super().accept()
