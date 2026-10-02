"""Qt task ownership and cooperative cancellation, independent of the current tab."""
from dataclasses import dataclass, field
import threading
from PyQt5 import QtCore, QtWidgets, sip


class OperationCancelled(Exception):
    pass


def check_cancelled(check):
    if check is not None and check():
        raise OperationCancelled('Operation canceled')


@dataclass(eq=False)
class ImageTask:
    tab: object
    view: object
    canvas: object
    file_path: str
    kind: str
    dialog: object = None
    settings: dict = field(default_factory=dict)
    cancelled: threading.Event = field(default_factory=threading.Event)
    workers: set = field(default_factory=set)

    def cancel(self):
        self.cancelled.set()
        for worker in list(self.workers):
            if not sip.isdeleted(worker):
                worker.requestInterruption()


class TaskManager(QtCore.QObject):
    def __init__(self, window):
        super().__init__(window)
        self.window = window
        self.active = {}
        self.workers = set()
        QtWidgets.QApplication.instance().aboutToQuit.connect(self.wait_for_shutdown)

    def begin(self, tab, kind, dialog=None, settings=None):
        view = tab.property('graphics_view')
        key = (id(view), kind)
        old = self.active.get(key)
        if old:
            old.cancel()
        task = ImageTask(tab, view, view.canvas, tab.property('file_path'), kind,
                         dialog, dict(settings or {}))
        self.active[key] = task
        if dialog is not None:
            dialog.rejected.connect(task.cancel)
        return task

    def valid(self, task):
        if task is None or task.cancelled.is_set():
            return False
        if self.active.get((id(task.view), task.kind)) is not task:
            return False
        if sip.isdeleted(task.tab) or (isinstance(task.view, QtCore.QObject) and sip.isdeleted(task.view)):
            return False
        return (self.window.tabWidget.indexOf(task.tab) >= 0
                and task.view.canvas is task.canvas
                and task.tab.property('file_path') == task.file_path)

    def start(self, task, worker):
        self.workers.add(worker)
        task.workers.add(worker)
        worker.finished.connect(lambda: self._release(task, worker))
        worker.start()

    def _release(self, task, worker):
        self.workers.discard(worker)
        task.workers.discard(worker)
        worker.deleteLater()

    def finish(self, task):
        if task is None:
            return
        key = (id(task.view), task.kind)
        if self.active.get(key) is task:
            del self.active[key]
        if task.dialog is not None and not sip.isdeleted(task.dialog):
            task.dialog.accept()
            task.dialog.deleteLater()

    def cancel_view(self, view):
        for task in list(self.active.values()):
            if task.view is view:
                task.cancel()
                self.finish(task)

    def cancel_all(self):
        for task in list(self.active.values()):
            task.cancel()
        for worker in list(self.workers):
            worker.requestInterruption()

    def running(self):
        return any(not sip.isdeleted(w) and w.isRunning() for w in self.workers)

    def wait_for_shutdown(self):
        self.cancel_all()
        for worker in list(self.workers):
            if not sip.isdeleted(worker):
                worker.wait()


def task_manager(window):
    if not hasattr(window, '_task_manager'):
        window._task_manager = TaskManager(window)
    return window._task_manager


def wait_for_worker(manager, task, worker, signal, canceled=lambda: False):
    """Batch stage: keep UI events running; return only after QThread.finished."""
    loop = QtCore.QEventLoop()
    received = []
    signal.connect(lambda *args: received.append(args))
    worker.finished.connect(loop.quit)
    timer = QtCore.QTimer()
    def poll():
        if canceled() or not manager.valid(task):
            task.cancel()
    timer.timeout.connect(poll)
    timer.start(25)
    manager.start(task, worker)
    loop.exec_()
    timer.stop()
    check_cancelled(lambda: canceled() or not manager.valid(task))
    if not received:
        raise RuntimeError('Worker finished without a result.')
    return received[-1]
