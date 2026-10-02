"""Short-lived GUI coalescing for annotation I/O; data stays on the Qt thread."""
from functools import wraps
from PyQt5 import QtCore, QtWidgets, sip
from task_support import OperationCancelled
import os
from collections import defaultdict
from safe_io import source_suffix
from dialog_ui import ResponsiveDialog


def image_path_key(path):
    return os.path.normcase(os.path.realpath(os.path.abspath(path))) if path else None


def mark_batch_fit(window):
    """Schedule one fit per existing image after any batch exit, including cancellation."""
    if not getattr(window, '_closing_requested', False):
        mark = getattr(window.tabWidget, 'mark_batch_fit', None)
        if mark is not None:
            mark()


def legacy_annotation_candidates(paths):
    """Index only exact stems and known exported prefixes."""
    candidates = defaultdict(list)
    prefixes = ('Polygon_Annotation_Batch_Exported_by_StomataQuant_',
                'Rectangle_Annotation_Batch_Exported_by_StomataQuant_',
                'Rotated_Rectangle_Annotation_Batch_Exported_by_StomataQuant_')
    for path in paths:
        stem = os.path.splitext(os.path.basename(path))[0]
        candidates[stem].append(path)
        for prefix in prefixes:
            if stem.startswith(prefix):
                candidates[stem[len(prefix):]].append(path)
    return candidates


def exact_annotation_candidates(paths, image_path, prefix, require_source_identity=False):
    stem = os.path.splitext(os.path.basename(image_path))[0]
    owned = f'{prefix}{stem}__{source_suffix(image_path)}'
    accepted = {owned} if require_source_identity else {stem, prefix + stem, owned}
    return [path for path in paths if os.path.splitext(os.path.basename(path))[0] in accepted]


class AnnotationBatch:
    def __init__(self, window, importing, restore_original):
        self.window = window
        self.importing = importing
        self.restore_original = restore_original
        self.original = window.tabWidget.currentWidget()
        self.last_new_tab = None
        self.progress = None
        self.changed = False
        self.connections = []
        self.import_results = None
        self.pipelined_measurements = False
        self.old_defer = getattr(window, '_defer_batch_refresh', False)
        timer = getattr(window, '_measurement_timer', None)
        self.measurement_pending = bool(timer and timer.isActive())

    def track(self, canvas):
        def changed(): self.changed = True
        canvas.shapesChanged.connect(changed)
        self.connections.append((canvas, changed))

    def checkpoint(self, tab=None, canvas=None):
        QtWidgets.QApplication.processEvents()
        if (getattr(self.window, '_closing_requested', False)
                or self.progress is not None and self.progress.wasCanceled()):
            raise OperationCancelled()
        if tab is not None and (sip.isdeleted(tab) or self.window.tabWidget.indexOf(tab) < 0
                                or canvas is not None and tab.property('graphics_view').canvas is not canvas):
            raise OperationCancelled()

    def finish(self):
        w = self.window
        try:
            target = self.original if self.restore_original or self.last_new_tab is None else self.last_new_tab
            if target is not None and not sip.isdeleted(target) and w.tabWidget.indexOf(target) >= 0:
                w.tabWidget.setCurrentWidget(target)
        finally:
            w._defer_batch_refresh = self.old_defer
            w._batch_running = False
            w._annotation_batch = None
            for canvas, callback in self.connections:
                if not sip.isdeleted(canvas):
                    try:
                        canvas.shapesChanged.disconnect(callback)
                    except (TypeError, RuntimeError):
                        # close_tab may already have disconnected every Canvas signal.
                        pass
            if self.progress is not None and not sip.isdeleted(self.progress):
                self.progress.close()
                self.progress.deleteLater()
        if not self.old_defer and hasattr(w, 'measurement_controller'):
            if self.importing and self.import_results is not None:
                if self.pipelined_measurements:
                    for index in range(w.tabWidget.count()):
                        w.measurement_controller.enqueue_batch_tab(w.tabWidget.widget(index))
                else:
                    w.measurement_controller.start_tabs()
            else:
                w.measurement_controller.refresh_tabs()
        if not self.old_defer and (self.changed or w.tabWidget.currentWidget() is not self.original):
            w.tabWidget._preserve_navigation_state = True
            try:
                w.update_list_on_tab_changed(w.tabWidget.currentIndex())
                w.update_zoom_on_tab_change(w.tabWidget.currentIndex())
                w.update_undo_button()
                w.update_actions_inToolBar()
            finally:
                w.tabWidget._preserve_navigation_state = False
        mark_batch_fit(w)
        if self.import_results is not None and not getattr(w, '_closing_requested', False):
            show_import_results(w, self.import_results)


def annotation_batch(importing=False, restore_original=False):
    def decorate(method):
        @wraps(method)
        def run(owner, *args, **kwargs):
            window = getattr(owner, 'main_window', owner)
            if getattr(window, '_batch_running', False):
                QtWidgets.QMessageBox.warning(window, 'Notice', 'Please wait for the current batch to finish.')
                return
            session = AnnotationBatch(window, importing, restore_original)
            window._annotation_batch = session
            window._batch_running = True
            window._defer_batch_refresh = True
            if hasattr(window, '_measurement_timer'):
                window._measurement_timer.stop()
            for i in range(window.tabWidget.count()):
                view = window.tabWidget.widget(i).property('graphics_view')
                if view and view.canvas:
                    session.track(view.canvas)
            try:
                return method(owner, *args, **kwargs)
            except OperationCancelled:
                if not getattr(window, '_closing_requested', False):
                    QtWidgets.QMessageBox.information(window, 'Batch canceled',
                        'Batch canceled. Completed images are retained; the current unfinished import was not added.')
            finally:
                session.finish()
        return run
    return decorate


def checkpoint(window, tab=None, canvas=None):
    session = getattr(window, '_annotation_batch', None)
    if session:
        session.checkpoint(tab, canvas)


class BatchImportResultsDialog(ResponsiveDialog):
    def __init__(self, window, results):
        super().__init__(window)
        self.setWindowTitle('Batch Import Results')
        self.setWindowModality(QtCore.Qt.NonModal)
        self.setAttribute(QtCore.Qt.WA_DeleteOnClose)
        self.setSizeGripEnabled(True)
        layout = QtWidgets.QVBoxLayout(self)
        self.summary = QtWidgets.QLabel('  |  '.join(
            f'{name.title()}: {results[name]}' for name in ('success', 'failed', 'missing', 'canceled')))
        self.summary.setWordWrap(True)
        self.summary.setTextInteractionFlags(QtCore.Qt.TextSelectableByMouse)
        layout.addWidget(self.summary)
        self.details = QtWidgets.QPlainTextEdit(self)
        self.details.setReadOnly(True)
        self.details.setLineWrapMode(QtWidgets.QPlainTextEdit.NoWrap)
        text = 'Successful files:\n' + '\n'.join(
            f'{image} ↔ {annotation}' for image, annotation in results['successful_files'])
        text += '\n\nErrors (file and line):\n' + '\n'.join(results['errors'])
        unmatched = results.get('unmatched_annotations', [])
        if unmatched:
            text += '\n\nUnmatched annotations:\n' + '\n'.join(unmatched)
        self.details.setPlainText(text)
        layout.addWidget(self.details, 1)
        self.buttons = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Ok, self)
        self.buttons.accepted.connect(self.accept)
        layout.addWidget(self.buttons)
        screen = window.screen() or QtWidgets.QApplication.primaryScreen()
        available = screen.availableGeometry()
        # Include room for the native window frame; text length never sets size.
        width, height = min(700, available.width() - 40), min(500, available.height() - 60)
        self.resize(max(1, width), max(1, height))
        self.move(available.center() - QtCore.QPoint(self.width() // 2, self.height() // 2))


def show_import_results(window, results):
    # Repeated imports otherwise stack identical-looking non-modal reports.
    # Closing the latest one reveals an older report and appears not to work.
    for previous in window.findChildren(BatchImportResultsDialog):
        previous.close()
    dialog = BatchImportResultsDialog(window, results)
    window._batch_import_results_dialog = dialog
    dialog.show()
    return dialog
