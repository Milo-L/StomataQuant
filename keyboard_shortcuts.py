"""One shortcut registry, native text editing, and focus-scoped annotation keys."""
from html import escape
from PyQt5 import QtCore, QtGui, QtWidgets
from dialog_ui import ResponsiveDialog


# Existing actions only; navigation actions below call existing tab/view methods.
BINDINGS = (
    ('actionOpen', 'Open images', ('Ctrl+O',), 'window'),
    ('actionClose', 'Close application', ('Ctrl+Q',), 'window'),
    ('actionUndo', 'Undo', ('Ctrl+Z',), 'image'),
    ('actionRedo', 'Redo', ('Ctrl+Y',), 'image'),
    ('actionDuplicate', 'Duplicate', ('Ctrl+D',), 'shapes'),
    ('actionDelete', 'Delete selected shapes', ('Delete',), 'shapes'),
    ('actionDeleteAllShapes', 'Clear All', ('Ctrl+Shift+Delete',), 'shapes'),
    ('actionCreatePolygon', 'Create Polygon', ('P',), 'image'),
    ('actionCreatePoint', 'Create Point', ('Shift+P',), 'image'),
    ('actionCreateRectangle', 'Create Rectangle', ('R',), 'image'),
    ('actionCreateRotatedRectangle', 'Create Rotated Rectangle', ('Shift+R',), 'image'),
    ('actionCreateLine', 'Create Line', ('L',), 'image'),
    ('actionEditShapes', 'Edit', ('E',), 'image'),
    ('actionGetMER', 'MER', ('Ctrl+G',), 'image'),
    ('actionZoom', 'Fit', ('Ctrl+0', 'Ctrl+Space'), 'image'),
    ('actionResetZoom', '1:1', ('Ctrl+1',), 'image'),
    ('actionAI', 'Run AI inference', ('Ctrl+I',), 'image'),
    ('actionModelSetting', 'Switch model', ('Ctrl+M',), 'command'),
    ('actionBatchProcessing', 'Batch Processing', ('Ctrl+B',), 'command'),
    ('actionShortcutHelp', 'Keyboard Shortcuts', ('F1',), 'window'),
)
CONTEXTS = {'window': 'Main window', 'command': 'Main window; outside text editors',
            'image': 'Current Tab; outside text editors', 'shapes': 'Canvas / ShapeList',
            'tabs': 'Open image Tabs'}


def key_sequence(event):
    key = event.key()
    modifiers = event.modifiers() & (QtCore.Qt.ControlModifier | QtCore.Qt.ShiftModifier |
                                    QtCore.Qt.AltModifier | QtCore.Qt.MetaModifier)
    if key == QtCore.Qt.Key_Backtab:
        key, modifiers = QtCore.Qt.Key_Tab, modifiers | QtCore.Qt.ShiftModifier
    if key == QtCore.Qt.Key_Plus:
        modifiers &= ~QtCore.Qt.ShiftModifier
    return QtGui.QKeySequence(int(modifiers) | key).toString(QtGui.QKeySequence.PortableText)


def text_editor(widget):
    while widget is not None:
        if isinstance(widget, (QtWidgets.QLineEdit, QtWidgets.QTextEdit, QtWidgets.QPlainTextEdit)):
            return True
        widget = widget.parentWidget()
    return False


class ShortcutHelpDialog(ResponsiveDialog):
    def __init__(self, window, rows):
        super().__init__(window)
        self.setWindowTitle('Keyboard Shortcuts')
        layout = QtWidgets.QVBoxLayout(self)
        browser = QtWidgets.QTextBrowser(self)
        browser.setHtml('<table cellpadding="6"><tr><th>Function</th><th>Shortcut</th><th>Context</th></tr>' +
                        ''.join('<tr>' + ''.join('<td>' + escape(value) + '</td>' for value in row) + '</tr>'
                                for row in rows) + '</table>')
        layout.addWidget(browser, 1)
        buttons = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Close, self)
        buttons.rejected.connect(self.close)
        layout.addWidget(buttons)


class ShortcutController(QtCore.QObject):
    def __init__(self, window):
        super().__init__(window)
        self.window = window
        self.entries = []
        self.keys = {}
        for attribute, title, keys, scope in BINDINGS:
            action = getattr(window, attribute)
            action.setShortcuts([QtGui.QKeySequence(key) for key in keys])
            action.setShortcutContext(QtCore.Qt.WindowShortcut)
            description = ('Generate Minimum Enclosing Rectangle' if attribute == 'actionGetMER'
                           else title)
            action.setToolTip(description + ' (' + ', '.join(keys) + ')')
            self._register(action, title, keys, scope)
        self._navigation('Next Tab', ('Ctrl+Tab', 'Ctrl+PgDown'), lambda: self._tab(1))
        self._navigation('Previous Tab', ('Ctrl+Shift+Tab', 'Ctrl+PgUp'), lambda: self._tab(-1))
        self._navigation('Close Tab', ('Ctrl+W',), self._close_tab)
        self._navigation('Search Tabs', ('Ctrl+F',), window.tabWidget.open_search)
        self._navigation('Zoom in', ('Ctrl++', 'Ctrl+='), lambda: self._zoom(True), 'image')
        self._navigation('Zoom out', ('Ctrl+-',), lambda: self._zoom(False), 'image')
        # These aliases have no window-wide Qt binding: result tables and text
        # editors retain their own native Ctrl+A / Ctrl+C actions.
        self._navigation('Select All Shapes', ('Ctrl+A',), self._select_all, 'shapes', routed=True)
        self._register(window.actionDuplicate, 'Duplicate (existing copy alias)', ('Ctrl+C',), 'shapes', routed=True)
        window.actionDuplicate.setToolTip('Duplicate (Ctrl+D; Ctrl+C in Canvas / ShapeList)')
        window.createToolButton.setToolTip('Create: P Polygon; Shift+P Point; R Rectangle; Shift+R Rotated Rectangle; L Line')
        window.zoomInButton.setToolTip('Zoom in (Ctrl++, Ctrl+=)')
        window.zoomOutButton.setToolTip('Zoom out (Ctrl+-)')
        window.modelSwitchButton.setToolTip('Select and load a model (Ctrl+M)')
        window.tabWidget.search_button.setToolTip('Search open image filenames (Ctrl+F)')
        window.actionEditShapes.setToolTip('Edit (E); Alt+click cycles overlapping shapes')
        for menu in window.findChildren(QtWidgets.QMenu):
            menu.setToolTipsVisible(True)
        QtWidgets.QApplication.instance().installEventFilter(self)

    def _register(self, action, title, keys, scope, routed=False):
        entry = dict(action=action, title=title, keys=keys, scope=scope, routed=routed)
        self.entries.append(entry)
        for key in keys:
            canonical = QtGui.QKeySequence(key).toString(QtGui.QKeySequence.PortableText)
            if canonical in self.keys:
                raise ValueError('Conflicting shortcut: ' + canonical)
            self.keys[canonical] = entry

    def _navigation(self, title, keys, callback, scope='tabs', routed=False):
        action = QtWidgets.QAction(title, self.window)
        action.setObjectName('shortcut_' + title.replace(' ', '_'))
        if not routed:
            action.setShortcuts([QtGui.QKeySequence(key) for key in keys])
            self.window.addAction(action)  # No menu/toolbar restructuring.
        action.setToolTip(title + ' (' + ', '.join(keys) + ')')
        action.triggered.connect(callback)
        self._register(action, title, keys, scope, routed)

    def _shape_focus(self, widget):
        view = self.window.get_current_graphics_view()
        table = self.window.shapedockinstance.table_widget
        return any(target is not None and (widget is target or target.isAncestorOf(widget))
                   for target in (view, table))

    def _measured_shape_focus(self, widget):
        dock = self.window.measured_results_dock
        return any(widget is table or table.isAncestorOf(widget)
                   for table in dock.findChildren(QtWidgets.QTableWidget))

    def eventFilter(self, widget, event):
        if (event.type() not in (QtCore.QEvent.ShortcutOverride, QtCore.QEvent.KeyPress)
                or not isinstance(widget, QtWidgets.QWidget)
                or isinstance(widget.window(), QtWidgets.QDialog)
                or not (widget is self.window or self.window.isAncestorOf(widget))):
            return False
        entry = self.keys.get(key_sequence(event))
        if entry is None:
            return False
        # Use the focused widget even if a key propagates to a parent view.
        focus = QtWidgets.QApplication.focusWidget() or widget
        editor = text_editor(focus)
        if entry['routed'] and (editor or not self._shape_focus(focus)):
            return False  # Native per-table/text Ctrl+A / Ctrl+C.
        if event.type() == QtCore.QEvent.ShortcutOverride:
            event.accept()
            return True  # One dispatcher; no ambiguous Qt action activation.
        if editor and entry['scope'] not in ('window', 'tabs'):
            return False  # Leave text editing to the widget after overriding global keys.
        shape_focus = self._shape_focus(focus)
        if entry['action'] is self.window.actionDelete:
            shape_focus = shape_focus or self._measured_shape_focus(focus)
        if entry['scope'] == 'shapes' and not shape_focus:
            return True
        if entry['scope'] == 'image' and self.window.get_current_graphics_view() is None:
            return True
        if entry['action'].isEnabled():
            entry['action'].trigger()
        event.accept()
        return True

    def _tab(self, direction):
        tabs = self.window.tabWidget
        if tabs.count():
            tabs.activate_image_tab((tabs.currentIndex() + direction) % tabs.count())

    def _close_tab(self):
        index = self.window.tabWidget.currentIndex()
        if index >= 0:
            self.window.close_tab(index)

    def _zoom(self, zoom_in):
        view = self.window.get_current_graphics_view()
        if view:
            (view.zoom_in if zoom_in else view.zoom_out)()

    def _select_all(self):
        view = self.window.get_current_graphics_view()
        if view and view.canvas:
            view.canvas.set_selected_shapes(list(view.canvas.shapes))

    def rows(self):
        rows = [(entry['title'], ' / '.join(entry['keys']), CONTEXTS[entry['scope']]) for entry in self.entries]
        rows.extend([('Select All', 'Ctrl+A', 'MeasuredResults / ResultsSummary / text editors'),
                     ('Copy', 'Ctrl+C', 'MeasuredResults / ResultsSummary / text editors'),
                     ('Edit metadata', 'F2', 'ShapeList'),
                     ('Cycle overlapping shapes', 'Alt+Left Click', 'Canvas, Edit mode'),
                     ('Zoom', 'Ctrl+Mouse Wheel', 'Current image view')])
        return rows


def shortcut_conflicts(window):
    """Detect duplicate Qt bindings whose focus/window scopes overlap."""
    bindings = []
    for obj in window.findChildren(QtWidgets.QAction) + window.findChildren(QtWidgets.QShortcut):
        if isinstance(obj, QtWidgets.QAction):
            keys, context = obj.shortcuts(), obj.shortcutContext()
        else:
            keys, context = [obj.key()], obj.context()
        parent = obj.parent()
        if not isinstance(parent, QtWidgets.QWidget):
            continue
        for key in keys:
            if not key.isEmpty():
                bindings.append((key.toString(QtGui.QKeySequence.PortableText), obj, context, parent))
    conflicts = []
    for index, (key, action, context, parent) in enumerate(bindings):
        for other_key, other, other_context, other_parent in bindings[index + 1:]:
            if key != other_key or action is other or parent.window() is not other_parent.window():
                continue
            narrow = (QtCore.Qt.WidgetShortcut, QtCore.Qt.WidgetWithChildrenShortcut)
            if context in narrow and other_context in narrow:
                overlap = parent is other_parent
                overlap |= context == QtCore.Qt.WidgetWithChildrenShortcut and parent.isAncestorOf(other_parent)
                overlap |= other_context == QtCore.Qt.WidgetWithChildrenShortcut and other_parent.isAncestorOf(parent)
                if not overlap:
                    continue
            conflicts.append((key, action.objectName() or type(action).__name__,
                              other.objectName() or type(other).__name__))
    return conflicts
