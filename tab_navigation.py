"""Image-tab navigation; retain Qt's existing scroll buttons and their connections."""
import os
from PyQt5 import QtCore, QtWidgets, sip
from dialog_ui import ResponsiveDialog


class TabSearchDialog(ResponsiveDialog):
    def __init__(self, tabs):
        super().__init__(tabs, QtCore.Qt.Popup)
        self.tabs = tabs
        self.setWindowTitle('Search open images')
        layout = QtWidgets.QVBoxLayout(self)
        self.query = QtWidgets.QLineEdit(self)
        self.query.setPlaceholderText('Search open image filenames…')
        self.results = QtWidgets.QListWidget(self)
        layout.addWidget(self.query)
        layout.addWidget(self.results)
        self.resize(420, 300)
        self.query.textChanged.connect(self.refilter)
        self.query.installEventFilter(self)
        self.results.itemClicked.connect(self.choose)
        self.results.itemActivated.connect(self.choose)
        self.refilter()

    def refilter(self):
        needle = self.query.text().casefold()
        self.results.clear()
        for index in range(self.tabs.count()):
            tab = self.tabs.widget(index)
            path = tab.property('file_path') or ''
            name = os.path.basename(path) if path else self.tabs.tabText(index)
            if needle in name.casefold():
                item = QtWidgets.QListWidgetItem(name)
                item.setToolTip(path)
                item.setData(QtCore.Qt.UserRole, tab)
                self.results.addItem(item)
        if self.results.count():
            self.results.setCurrentRow(0)

    def eventFilter(self, obj, event):
        if obj is self.query and event.type() == QtCore.QEvent.KeyPress:
            if event.key() in (QtCore.Qt.Key_Down, QtCore.Qt.Key_Up):
                delta = 1 if event.key() == QtCore.Qt.Key_Down else -1
                row = max(0, min(self.results.count()-1, self.results.currentRow()+delta))
                self.results.setCurrentRow(row)
                return True
            if event.key() in (QtCore.Qt.Key_Return, QtCore.Qt.Key_Enter):
                self.choose(self.results.currentItem())
                return True
        return super().eventFilter(obj, event)

    def choose(self, item):
        if item is None:
            return
        tab = item.data(QtCore.Qt.UserRole)
        if tab is not None and not sip.isdeleted(tab):
            index = self.tabs.indexOf(tab)
            if index >= 0:
                self.tabs.activate_image_tab(index)
                self.accept()
                return
        self.refilter()


class NavigableTabWidget(QtWidgets.QTabWidget):
    tabCountChanged = QtCore.pyqtSignal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setUsesScrollButtons(True)
        bar = self.tabBar()
        buttons = bar.findChildren(QtWidgets.QToolButton)
        # Qt 5 creates left then right, but leaves arrowType=NoArrow until overflow.
        self.previous_button, self.next_button = buttons
        self.previous_button.setArrowType(QtCore.Qt.LeftArrow)
        self.next_button.setArrowType(QtCore.Qt.RightArrow)
        # Keep the exact native objects: no replacement buttons or clicked connections.
        self.navigation = QtWidgets.QWidget(self)
        layout = QtWidgets.QHBoxLayout(self.navigation)
        layout.setContentsMargins(2, 0, 0, 0)
        layout.setSpacing(2)
        self.first_button = QtWidgets.QToolButton(self.navigation)
        self.search_button = QtWidgets.QToolButton(self.navigation)
        self.last_button = QtWidgets.QToolButton(self.navigation)
        self.first_button.setText('First')
        self.search_button.setText('Search')
        self.last_button.setText('Last')
        for button, width, tip in [(self.first_button,40,'Activate first image'),
                                   (self.previous_button,22,'Scroll tab bar left'),
                                   (self.search_button,52,'Search open image filenames'),
                                   (self.next_button,22,'Scroll tab bar right'),
                                   (self.last_button,40,'Activate last image')]:
            width = max(width, button.fontMetrics().horizontalAdvance(button.text()) + 12)
            button.setFixedSize(width, max(26, button.fontMetrics().height() + 8))
            button.setToolTip(tip)
            layout.addWidget(button)
        self.navigation.setFixedWidth(sum(layout.itemAt(i).widget().width() for i in range(layout.count())) + 10)
        self.setCornerWidget(self.navigation, QtCore.Qt.TopRightCorner)
        self.first_button.clicked.connect(lambda: self.activate_image_tab(0))
        self.last_button.clicked.connect(lambda: self.activate_image_tab(self.count()-1))
        self.search_button.clicked.connect(self.open_search)
        self.currentChanged.connect(self._queue_sync)
        self.tabBar().tabMoved.connect(self._queue_sync)
        self._pending = False
        self._syncing = False
        self._fit_queued = False
        self._batch_fit_generation = 0
        self.currentChanged.connect(self._queue_batch_fit)
        for obj in (bar, self.previous_button, self.next_button):
            obj.installEventFilter(self)
        self._sync_navigation()

    def tabInserted(self, index):
        super().tabInserted(index)
        self.tabCountChanged.emit(self.count())
        if hasattr(self, 'first_button'):
            self._queue_sync()

    def tabRemoved(self, index):
        super().tabRemoved(index)
        self.tabCountChanged.emit(self.count())
        if hasattr(self, 'first_button'):
            self._queue_sync()

    def _queue_sync(self, *args):
        if not self._pending and not self._syncing:
            self._pending = True
            QtCore.QTimer.singleShot(0, self._sync_navigation)

    def eventFilter(self, obj, event):
        if event.type() in (QtCore.QEvent.Resize, QtCore.QEvent.Move, QtCore.QEvent.Show,
                            QtCore.QEvent.Hide, QtCore.QEvent.LayoutRequest):
            self._queue_sync()
            self._queue_batch_fit()
        return super().eventFilter(obj, event)

    def mark_batch_fit(self):
        """Mark existing pages only; never activate or fit hidden pages here."""
        self._batch_fit_generation += 1
        for index in range(self.count()):
            page = self.widget(index)
            view = page.property('graphics_view')
            if view is None or sip.isdeleted(view):
                continue
            page.setProperty('_batch_fit_pending', self._batch_fit_generation)
            if not view.property('_batch_fit_watched'):
                view.viewport().installEventFilter(self)
                view.setProperty('_batch_fit_watched', True)
        self._queue_batch_fit()

    def _queue_batch_fit(self, *args):
        page = self.currentWidget()
        if (not self._fit_queued and page is not None
                and page.property('_batch_fit_pending')):
            self._fit_queued = True
            QtCore.QTimer.singleShot(0, self._prepare_batch_fit)

    def _prepare_batch_fit(self):
        if sip.isdeleted(self):
            return
        page = self.currentWidget()
        if page is not None and page.layout() is not None:
            page.layout().activate()
        # Let stacked-page layout and viewport resize events settle first.
        QtCore.QTimer.singleShot(0, self._apply_batch_fit)

    def _apply_batch_fit(self):
        if sip.isdeleted(self):
            return
        self._fit_queued = False
        page = self.currentWidget()
        if page is None or not page.property('_batch_fit_pending'):
            return
        view = page.property('graphics_view')
        if (view is None or sip.isdeleted(view) or not view.isVisible()
                or view.viewport().width() <= 1 or view.viewport().height() <= 1
                or view.pixmap_item is None or view.pixmap_item.pixmap().isNull()):
            # Hidden/minimized/unlaid-out pages retry on Show/Resize, without polling.
            return
        # Consume before fit: scrollbar/viewport resize events must not refit again.
        page.setProperty('_batch_fit_pending', None)
        view.fit_to_view_custom()
        view.centerOn(view.pixmap_item.sceneBoundingRect().center())

    def _sync_navigation(self):
        if sip.isdeleted(self):
            return
        self._pending = False
        self._syncing = True
        try:
            index = self.currentIndex()
            self.first_button.setEnabled(index > 0)
            self.last_button.setEnabled(0 <= index < self.count()-1)
            self.search_button.setEnabled(self.count() > 0)
            for button in (self.previous_button, self.next_button):
                button.show()
            self.navigation.layout().invalidate()
            self.navigation.layout().activate()
            bar = self.tabBar()
            extent = bar.tabRect(self.count()-1).right() - bar.tabRect(0).left() + 1 if self.count() else 0
            if extent <= bar.width():
                self.previous_button.setEnabled(False)
                self.next_button.setEnabled(False)
            # With overflow, Qt itself maintains native enabled states and scroll limits.
        finally:
            self._syncing = False

    def activate_image_tab(self, index):
        if not 0 <= index < self.count():
            return
        # The normal main-window tab callback refreshes lists; preserve edit selection.
        self._preserve_navigation_state = True
        try:
            self.setCurrentIndex(index)
        finally:
            self._preserve_navigation_state = False
        self._queue_sync()

    def open_search(self):
        if not self.count():
            return
        if getattr(self, 'search_dialog', None) is not None:
            self.search_dialog.close()
            self.search_dialog.deleteLater()
        self.search_dialog = TabSearchDialog(self)
        self.search_dialog.move(self.search_button.mapToGlobal(QtCore.QPoint(0, self.search_button.height())))
        self.search_dialog.show()
        self.search_dialog.query.setFocus()
