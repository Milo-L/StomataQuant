"""Local toolbar/status presentation helpers; no application actions live here."""
from PyQt5 import QtCore, QtGui, QtWidgets


class PersistentStatusBar(QtWidgets.QStatusBar):
    """Keep the image/model groups visible while a transient message is shown."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._message_text = ''
        self._message_label = None
        self._message_timer = QtCore.QTimer(self)
        self._message_timer.setSingleShot(True)
        self._message_timer.timeout.connect(self.clearMessage)

    def attach_message_label(self, label):
        self._message_label = label
        label.hide()

    def showMessage(self, message, timeout=0):
        if self._message_label is None:
            return super().showMessage(message, timeout)
        self._message_timer.stop()
        message = str(message)
        self._message_text = message
        self._message_label.setText(message)
        self._message_label.setToolTip(message)
        self._message_label.setVisible(bool(message))
        self.messageChanged.emit(message)
        if message and timeout > 0:
            self._message_timer.start(timeout)

    def clearMessage(self):
        if self._message_label is None:
            return super().clearMessage()
        self._message_timer.stop()
        if self._message_text:
            self._message_text = ''
            self._message_label.clear()
            self._message_label.hide()
            self.messageChanged.emit('')

    def currentMessage(self):
        if self._message_label is None:
            return super().currentMessage()
        return self._message_text


def line_icon(kind):
    """Small, matching Qt-painted icons at several resolutions (no assets needed)."""
    icon = QtGui.QIcon()
    palette = QtWidgets.QApplication.palette()
    text_color = palette.color(QtGui.QPalette.Active, QtGui.QPalette.ButtonText)
    disabled_color = palette.color(QtGui.QPalette.Disabled, QtGui.QPalette.ButtonText)
    for mode, state, color in (
        (QtGui.QIcon.Normal, QtGui.QIcon.Off, text_color),
        (QtGui.QIcon.Normal, QtGui.QIcon.On, text_color),
        (QtGui.QIcon.Disabled, QtGui.QIcon.Off, disabled_color),
        (QtGui.QIcon.Disabled, QtGui.QIcon.On, disabled_color),
    ):
        for size in (16, 24, 32, 48, 64):
            pixmap = QtGui.QPixmap(size, size)
            pixmap.fill(QtCore.Qt.transparent)
            p = QtGui.QPainter(pixmap)
            p.setRenderHint(QtGui.QPainter.Antialiasing)
            p.scale(size / 24., size / 24.)
            p.setPen(QtGui.QPen(QtGui.QColor(color), 2.0, QtCore.Qt.SolidLine,
                               QtCore.Qt.RoundCap, QtCore.Qt.RoundJoin))

            def line(x1, y1, x2, y2):
                p.drawLine(QtCore.QPointF(x1, y1), QtCore.QPointF(x2, y2))

            def poly(points):
                p.drawPolyline(QtGui.QPolygonF([QtCore.QPointF(*xy) for xy in points]))

            if kind in ('create', 'plus', 'minus'):
                line(5, 12, 19, 12)
                if kind != 'minus':
                    line(12, 5, 12, 19)
            elif kind == 'edit':
                poly([(4, 20), (5, 15), (16, 4), (20, 8), (9, 19), (4, 20)])
                line(14, 6, 18, 10)
            elif kind == 'mer':
                p.drawRect(QtCore.QRectF(3, 5, 18, 14))
                poly([(6, 15), (10, 8), (17, 11), (15, 16), (6, 15)])
            elif kind == 'copy':
                p.drawRoundedRect(QtCore.QRectF(8, 8, 12, 13), 1, 1)
                poly([(15, 5), (15, 3), (3, 3), (3, 16), (5, 16)])
            elif kind in ('delete', 'clear'):
                line(4, 6, 20, 6)
                poly([(9, 6), (9, 3), (15, 3), (15, 6)])
                poly([(6, 6), (7, 21), (17, 21), (18, 6)])
                if kind == 'delete':
                    line(10, 10, 10, 17)
                    line(14, 10, 14, 17)
                else:
                    line(10, 11, 14, 16)
                    line(14, 11, 10, 16)
            elif kind == 'fit':
                for points in ([(3, 9), (3, 3), (9, 3)], [(15, 3), (21, 3), (21, 9)],
                               [(21, 15), (21, 21), (15, 21)], [(9, 21), (3, 21), (3, 15)]):
                    poly(points)
                p.drawRect(QtCore.QRectF(8, 8, 8, 8))
            elif kind == 'actual':
                p.drawRect(QtCore.QRectF(4, 4, 16, 16))
                p.drawRect(QtCore.QRectF(10, 10, 4, 4))
            elif kind == 'switch':
                line(4, 7, 20, 7)
                poly([(16, 3), (20, 7), (16, 11)])
                line(20, 17, 4, 17)
                poly([(8, 13), (4, 17), (8, 21)])
            p.end()
            icon.addPixmap(pixmap, mode, state)
    return icon


def style_button(button, icon_only=False, destructive=False):
    # Use the same native auto-raised toolbutton style as the existing AI action.
    button.setProperty('sqControl', True)
    button.setProperty('sqDestructive', destructive)
    button.setAutoRaise(True)
    toolbar = getattr(button.window(), 'toolBar', None)
    if toolbar is not None:
        button.setIconSize(toolbar.iconSize())
    button.setToolButtonStyle(QtCore.Qt.ToolButtonIconOnly if icon_only
                              else QtCore.Qt.ToolButtonTextBesideIcon)
    button.setSizePolicy(QtWidgets.QSizePolicy.Preferred, QtWidgets.QSizePolicy.Preferred)


class StatusValueLabel(QtWidgets.QLabel):
    """Keep the full status value while displaying an ellipsis in narrow windows."""
    def setText(self, text):
        super().setText(text)
        self.setToolTip(text)

    def minimumSizeHint(self):
        size = super().minimumSizeHint()
        size.setWidth(0)
        return size

    def paintEvent(self, event):
        painter = QtGui.QPainter(self)
        painter.setPen(self.palette().color(QtGui.QPalette.WindowText))
        text = self.fontMetrics().elidedText(self.text(), QtCore.Qt.ElideRight,
                                             max(0, self.contentsRect().width()))
        painter.drawText(self.contentsRect(), QtCore.Qt.AlignLeft | QtCore.Qt.AlignVCenter, text)


class PathStatusLabel(StatusValueLabel):
    """Show the active image path without letting long directories crowd the status bar."""

    def paintEvent(self, event):
        painter = QtGui.QPainter(self)
        painter.setPen(self.palette().color(QtGui.QPalette.WindowText))
        text = self.fontMetrics().elidedText(self.text(), QtCore.Qt.ElideMiddle,
                                             max(0, self.contentsRect().width()))
        painter.drawText(self.contentsRect(), QtCore.Qt.AlignLeft | QtCore.Qt.AlignVCenter, text)


class ModelLabel(QtWidgets.QLabel):
    """Keep long model filenames from pushing image status out of the window."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self._full_text = 'Model: None'
        self.setMinimumWidth(70)
        self.setMaximumWidth(460)
        self.setSizePolicy(QtWidgets.QSizePolicy.Preferred, QtWidgets.QSizePolicy.Preferred)
        self.setModelText(self._full_text)

    def setModelText(self, text):
        self._full_text = text
        self.setToolTip(text)
        self._elide()
        self.updateGeometry()

    def _elide(self):
        super().setText(self.fontMetrics().elidedText(self._full_text, QtCore.Qt.ElideMiddle,
                                                     max(0, self.contentsRect().width())))

    def sizeHint(self):
        size = super().sizeHint()
        size.setWidth(min(self.maximumWidth(), self.fontMetrics().horizontalAdvance(self._full_text) + 4))
        return size

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._elide()


class NativeChrome(QtCore.QObject):
    """Keep the AI font/theme and adapt spacing, icons and flexible fields to width."""
    def __init__(self, window):
        super().__init__(window)
        self.window = window
        self.ai_button = window.toolBar.widgetForAction(window.actionAI)
        self.ai_icon_size = self.ai_button.iconSize()
        self.pending = False
        for widget in (window, window.toolBar, window.statusbar):
            widget.installEventFilter(self)
        self.refresh()

    def eventFilter(self, watched, event):
        if event.type() in (QtCore.QEvent.Resize, QtCore.QEvent.Show,
                            QtCore.QEvent.FontChange, QtCore.QEvent.ApplicationFontChange,
                            QtCore.QEvent.StyleChange):
            if not self.pending:
                self.pending = True
                QtCore.QTimer.singleShot(0, self.refresh)
        return False

    def refresh(self):
        self.pending = False
        w = self.window
        font = self.ai_button.font()
        metrics = QtGui.QFontMetrics(font)
        width = max(1, w.toolBar.width())
        scale = max(.75, min(1., width / 1500.))
        icon_size = max(16, round((metrics.height() - 2) * scale))
        spacing = max(1, round(4 * scale))
        toolbar_style = 'QToolBar#toolBar { spacing: %dpx; padding: 1px %dpx; }' % (spacing, spacing)
        if w.toolBar.styleSheet() != toolbar_style:
            w.toolBar.setStyleSheet(toolbar_style)
        w.toolBar.setIconSize(QtCore.QSize(icon_size, icon_size))
        self.ai_button.setIconSize(self.ai_icon_size)
        row_height = max(self.ai_button.sizeHint().height(), metrics.height() + 8, icon_size + 8)
        text_buttons = []
        for action in w.toolBar.actions():
            button = w.toolBar.widgetForAction(action)
            if isinstance(button, QtWidgets.QToolButton) and button.property('sqControl'):
                button.setFont(font)
                button.setIconSize(QtCore.QSize(icon_size, icon_size))
                button.setMinimumHeight(row_height)
                if button.toolButtonStyle() == QtCore.Qt.ToolButtonIconOnly:
                    if action in (w.actionUndo, getattr(w, 'actionRedo', None)) or button in (w.zoomOutButton, w.zoomInButton):
                        button.setFixedWidth(row_height)
                    else:
                        text_buttons.append(button)
                else:
                    text_buttons.append(button)
        for button in text_buttons:
            button.setMinimumWidth(0)
            button.setMaximumWidth(16777215)
            button.setToolButtonStyle(QtCore.Qt.ToolButtonTextBesideIcon)
        w.toolBar.setMinimumHeight(row_height + 6)
        w.zoomLineEdit.setFont(font)
        w.zoomLineEdit.setFixedWidth(metrics.horizontalAdvance('1000%') + 12)
        w.zoomLineEdit.setMinimumHeight(row_height)
        w.zoomSlider.setMinimumWidth(max(48, round(metrics.height() * 2)))
        w.zoomSlider.setMaximumWidth(max(80, min(240, round(width * .14))))
        def required_width():
            total = 12 + spacing * max(0, len(w.toolBar.actions()) - 1)
            for action in w.toolBar.actions():
                widget = w.toolBar.widgetForAction(action)
                if widget is not None:
                    if widget is w.zoomSlider:
                        total += widget.minimumWidth()
                    elif widget.minimumWidth() == widget.maximumWidth():
                        total += widget.minimumWidth()
                    else:
                        total += widget.sizeHint().width()
            return total

        # Keep readable AI-sized text. In narrower windows, secondary commands
        # become icon buttons with their existing action tooltips, rather than
        # shrinking fonts or hiding the zoom controls in Qt's overflow menu.
        for action in (w.actionDuplicate, w.actionDeleteAllShapes, w.actionDelete,
                       w.actionGetMER, w.actionEditShapes, w.actionResetZoom, w.actionZoom):
            if required_width() <= width - 12:
                break
            button = w.toolBar.widgetForAction(action)
            button.setToolButtonStyle(QtCore.Qt.ToolButtonIconOnly)
            button.setFixedWidth(row_height)
        for label in (w.pathLabel, w.imageSizeLabel, w.fileSizeLabel, w.scaleLabel, w.mousePositionLabel,
                      w.pixelValueLabel, w.tabsCountLabel, w.modelLabel):
            label.setFont(font)
        w.pathLabel.setMaximumWidth(max(90, min(320, round(w.width() * .22))))
        w.modelLabel.setMaximumWidth(max(120, min(520, round(w.width() * .26))))
        w.modelLabel.setMinimumWidth(metrics.horizontalAdvance('Model: None') + 4)
        w.modelLabel._elide()
        w.modelSwitchButton.setFont(font)
        w.modelSwitchButton.setIconSize(QtCore.QSize(icon_size, icon_size))
        w.modelSwitchButton.setMinimumHeight(row_height)
        for layout in (w.statusInfoWidget.layout(), w.modelStatusWidget.layout()):
            layout.setSpacing(max(4, round(metrics.height() * .3 * scale)))
        for separator in w._status_separators:
            separator.setFixedHeight(max(14, round(metrics.height() * .7)))
        w.statusbar.setMinimumHeight(row_height + 4)


def configure_chrome(window):
    toolbar = window.toolBar
    toolbar.setStyleSheet('')
    window.createToolButton.setObjectName('sqCreate')
    window.createToolButton.setIcon(line_icon('create'))
    style_button(window.createToolButton)
    for action, kind in ((window.actionEditShapes, 'edit'), (window.actionGetMER, 'mer'),
                         (window.actionDuplicate, 'copy'), (window.actionDelete, 'delete'),
                         (window.actionDeleteAllShapes, 'clear'), (window.actionZoom, 'fit'),
                         (window.actionResetZoom, 'actual')):
        action.setIcon(line_icon(kind))
        style_button(toolbar.widgetForAction(action), destructive=kind in ('delete', 'clear'))
    style_button(toolbar.widgetForAction(window.actionUndo), icon_only=True)
    for button, kind in ((window.zoomOutButton, 'minus'), (window.zoomInButton, 'plus')):
        button.setIcon(line_icon(kind))
        style_button(button, icon_only=True)
    window.zoomSlider.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Preferred)
    window.zoomLineEdit.setObjectName('sqZoomPercent')
    window.zoomLineEdit.setStyleSheet('QLineEdit { background: transparent; border: none; }')
    window.zoomLineEdit.setFrame(False)
    window.zoomLineEdit.setAlignment(QtCore.Qt.AlignCenter)
    window.zoomLineEdit.setToolTip('Zoom percentage (10-1000%)')

    status = window.statusbar
    # Remove Qt's individual status-item frames without adding a custom background/theme.
    status.setStyleSheet('QStatusBar::item { border: none; }')
    window._status_separators = []

    def add_separator(layout, parent):
        separator = QtWidgets.QFrame(parent)
        separator.setFrameShape(QtWidgets.QFrame.VLine)
        separator.setFrameShadow(QtWidgets.QFrame.Plain)
        separator.setFixedWidth(1)
        window._status_separators.append(separator)
        layout.addWidget(separator)

    window.statusInfoWidget = QtWidgets.QWidget(status)
    window.statusInfoWidget.setSizePolicy(QtWidgets.QSizePolicy.Maximum, QtWidgets.QSizePolicy.Preferred)
    layout = QtWidgets.QHBoxLayout(window.statusInfoWidget)
    layout.setContentsMargins(6, 0, 6, 0)
    labels = (window.pathLabel, window.imageSizeLabel, window.fileSizeLabel, window.scaleLabel,
              window.mousePositionLabel, window.pixelValueLabel)
    for index, label in enumerate(labels):
        if index:
            add_separator(layout, window.statusInfoWidget)
        label.setMinimumWidth(0)
        label.setSizePolicy(QtWidgets.QSizePolicy.Preferred, QtWidgets.QSizePolicy.Preferred)
        label.setToolTip(label.text())
        layout.addWidget(label)
    status.addPermanentWidget(window.statusInfoWidget)
    # The sole expanding spacer is between the two compact information groups.
    window.statusSpacer = QtWidgets.QWidget(status)
    window.statusSpacer.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Preferred)
    message_layout = QtWidgets.QHBoxLayout(window.statusSpacer)
    message_layout.setContentsMargins(8, 0, 8, 0)
    window.statusMessageLabel = QtWidgets.QLabel(window.statusSpacer)
    window.statusMessageLabel.setSizePolicy(QtWidgets.QSizePolicy.Ignored, QtWidgets.QSizePolicy.Preferred)
    window.statusMessageLabel.setMinimumWidth(0)
    window.statusMessageLabel.setAlignment(QtCore.Qt.AlignCenter)
    message_layout.addWidget(window.statusMessageLabel)
    status.attach_message_label(window.statusMessageLabel)
    status.addPermanentWidget(window.statusSpacer, 1)
    window.modelStatusWidget = QtWidgets.QWidget(status)
    window.modelStatusWidget.setSizePolicy(QtWidgets.QSizePolicy.Maximum, QtWidgets.QSizePolicy.Preferred)
    model_layout = QtWidgets.QHBoxLayout(window.modelStatusWidget)
    model_layout.setContentsMargins(4, 0, 6, 0)
    window.tabsCountLabel = StatusValueLabel(f'Tabs: {window.tabWidget.count()}', window.modelStatusWidget)
    window.tabsCountLabel.setSizePolicy(QtWidgets.QSizePolicy.Fixed, QtWidgets.QSizePolicy.Preferred)
    window.tabWidget.tabCountChanged.connect(lambda count: window.tabsCountLabel.setText(f'Tabs: {count}'))
    model_layout.addWidget(window.tabsCountLabel)
    add_separator(model_layout, window.modelStatusWidget)
    window.modelLabel = ModelLabel(window.modelStatusWidget)
    model_layout.addWidget(window.modelLabel)
    window.modelSwitchButton = QtWidgets.QToolButton(window.modelStatusWidget)
    window.modelSwitchButton.setObjectName('sqModelSwitch')
    window.modelSwitchButton.setText('Switch')
    window.modelSwitchButton.setToolTip('Select and load a model')
    window.modelSwitchButton.setIcon(line_icon('switch'))
    window.modelSwitchButton.setToolButtonStyle(QtCore.Qt.ToolButtonTextBesideIcon)
    window.modelSwitchButton.setAutoRaise(True)
    window.modelSwitchButton.clicked.connect(window.actionModelSetting.trigger)
    add_separator(model_layout, window.modelStatusWidget)
    model_layout.addWidget(window.modelSwitchButton)
    status.addPermanentWidget(window.modelStatusWidget)
    window._native_chrome = NativeChrome(window)
