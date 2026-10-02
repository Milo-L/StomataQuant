"""Shared sizing and scrolling for custom dialogs; button signals stay unchanged."""
from PyQt5 import QtCore, QtWidgets


DEFAULT_SIZES = {
    'BatchProcessingDialog': (640, 700), 'BatchProgressDialog': (560, 280),
    'InferenceSettingsDialog': (600, 620), 'LabelInputDialog': (420, 240),
    'ProgressDialog': (440, 180), 'ColorSettingsDialog': (420, 440),
    'DisplaySettingsDialog': (580, 500), 'HeatMapDialog': (580, 440),
    'AnnotationMatchDialog': (850, 520), 'SetMeasuringScaleDialog': (820, 740),
    'TabSearchDialog': (420, 300), 'BatchImportResultsDialog': (700, 500),
    'ShortcutHelpDialog': (720, 520),
}


class ButtonRow(QtWidgets.QWidget):
    """Wrap action-button rows on narrow screens instead of setting a wide minimum."""
    def __init__(self, widgets, parent):
        super().__init__(parent)
        self.widgets = widgets
        self.grid = QtWidgets.QGridLayout(self)
        self.grid.setContentsMargins(0, 0, 0, 0)
        self._columns = 0
        self._reflow(500)

    def _reflow(self, width):
        slot = max(widget.sizeHint().width() for widget in self.widgets) + self.grid.horizontalSpacing()
        columns = max(1, min(len(self.widgets), width // max(1, slot)))
        if columns == self._columns:
            return
        self._columns = columns
        while self.grid.count():
            self.grid.takeAt(0)
        for index, widget in enumerate(self.widgets):
            self.grid.addWidget(widget, index // columns, index % columns)
        self.updateGeometry()

    def minimumSizeHint(self):
        size = super().minimumSizeHint()
        size.setWidth(0)
        return size

    def resizeEvent(self, event):
        self._reflow(event.size().width())
        super().resizeEvent(event)


def _button_widgets(item):
    widget = item.widget()
    if widget is not None:
        return [widget] if isinstance(widget, (QtWidgets.QPushButton, QtWidgets.QDialogButtonBox)) else []
    layout = item.layout()
    if layout is None:
        return []
    buttons = []
    for index in range(layout.count()):
        child = layout.itemAt(index)
        if child.spacerItem() is not None:
            continue
        found = _button_widgets(child)
        if not found:
            return []
        buttons.extend(found)
    return buttons


class ResponsiveDialog(QtWidgets.QDialog):
    def showEvent(self, event):
        if not getattr(self, '_dialog_prepared', False):
            self._prepare_dialog()
        self._fit_screen(initial=not getattr(self, '_dialog_shown', False))
        self._dialog_shown = True
        super().showEvent(event)

    def _prepare_dialog(self):
        self._dialog_prepared = True
        original = QtWidgets.QWidget.layout(self)
        if original is None:
            return
        footers = []
        for index in reversed(range(original.count())):
            item = original.itemAt(index)
            buttons = _button_widgets(item)
            if buttons:
                taken = original.takeAt(index)
                footers.append((taken, buttons))
        self._dialog_content = QtWidgets.QWidget()
        # QWidget.setLayout transfers the layout from its previous widget.
        self._dialog_content.setLayout(original)
        root = QtWidgets.QVBoxLayout(self)
        self._dialog_scroll = QtWidgets.QScrollArea(self)
        self._dialog_scroll.setFrameShape(QtWidgets.QFrame.NoFrame)
        self._dialog_scroll.setWidgetResizable(True)
        self._dialog_scroll.setWidget(self._dialog_content)
        self._dialog_scroll.setMinimumSize(0, 0)
        root.addWidget(self._dialog_scroll, 1)
        self._dialog_buttons = []
        for item, buttons in reversed(footers):
            if item.widget() is not None:
                root.addWidget(item.widget(), 0, QtCore.Qt.AlignRight)
            else:
                for button in buttons:
                    item.layout().removeWidget(button)
                root.addWidget(ButtonRow(buttons, self))
                item.layout().deleteLater()
            self._dialog_buttons.extend(buttons)
        for label in self._dialog_content.findChildren(QtWidgets.QLabel):
            if label.pixmap() is None or label.pixmap().isNull():
                label.setWordWrap(True)
                label.setSizePolicy(QtWidgets.QSizePolicy.Ignored, QtWidgets.QSizePolicy.Preferred)
        self.setMinimumSize(0, 0)
        self.setSizeGripEnabled(True)
        self.setWindowFlag(QtCore.Qt.MSWindowsFixedSizeDialogHint, False)

    def _fit_screen(self, initial=False):
        screen = self.screen() or QtWidgets.QApplication.primaryScreen()
        available = screen.availableGeometry()
        bounds = available.adjusted(12, 24, -12, -24)
        self.setMaximumSize(bounds.size())
        if initial:
            desired = DEFAULT_SIZES.get(type(self).__name__, (560, 420))
            self.resize(min(desired[0], int(available.width() * .9), bounds.width()),
                        min(desired[1], int(available.height() * .85), bounds.height()))
        else:
            self.resize(min(self.width(), bounds.width()), min(self.height(), bounds.height()))
        if initial and not self.windowFlags() & QtCore.Qt.Popup:
            parent = self.parentWidget()
            center = parent.frameGeometry().center() if parent is not None else available.center()
            QtWidgets.QWidget.move(self, center - QtCore.QPoint(self.width() // 2, self.height() // 2))
        QtWidgets.QWidget.move(self, max(bounds.left(), min(self.x(), bounds.right() - self.width() + 1)),
                              max(bounds.top(), min(self.y(), bounds.bottom() - self.height() + 1)))
