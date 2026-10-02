"""Canvas change journal -> ID rows/statistics, with cancellable bulk jobs.

Only the GUI thread reads live Shapes. Workers own value-only geometry snapshots
and reuse the original scientific functions without constructing QGraphicsItems.
"""
import queue
import math
import threading
import time
import weakref
from types import SimpleNamespace
from PyQt5 import QtCore, QtWidgets, sip
from shape import Shape
from measurements import ensure_features, resolve_scale, measurement_key
from measurement_summary import IncrementalSummary, SummaryRows


class GeometrySnapshot(SimpleNamespace):
    # Class methods avoid per-snapshot closure cycles retaining large point lists.
    get_center = Shape.get_center
    sync_rotated_angle = Shape.sync_rotated_angle


def calculate_snapshot(snapshot, scale):
    uid, revision, kind, label, group, coordinates = snapshot
    geometry = GeometrySnapshot(shape_type=kind, label=label, group_id=group,
        pointslist=[QtCore.QPointF(x, y) for x, y in coordinates], feature_results={},
        unit='pixel' if kind == 'point' else (scale or {}).get('unit', 'pixel'),
        rotated_angle=0., _measurement_scale=None, _measurement_key=None)
    error = None
    try:
        getattr(Shape, 'feature_extraction_' + kind)(geometry, scale)
    except Exception as exc:
        geometry.feature_results = {}
        error = str(exc)
    return uid, revision, dict(geometry.feature_results), geometry.unit, geometry._measurement_key, error


class BulkWorker(QtCore.QThread):
    def __init__(self, scale, parent):
        super().__init__(parent)
        self.scale = dict(scale) if scale else None
        self.inputs, self.outputs = queue.Queue(32), queue.Queue(32)
        self.cancelled = threading.Event()

    def run(self):
        while not self.cancelled.is_set():
            try:
                snapshot = self.inputs.get(timeout=.05)
            except queue.Empty:
                continue
            if snapshot is None:
                return
            result = calculate_snapshot(snapshot, self.scale)
            while not self.cancelled.is_set():
                try:
                    self.outputs.put(result, timeout=.05)
                    break
                except queue.Full:
                    pass


class MeasurementController(QtCore.QObject):
    # A conservative threshold; complex one-off Shapes still use the sync path.
    async_threshold = 64
    cancelled_notice = ('Measurements cancelled; remaining results are incomplete. '
                        'Returning to this image resumes the update.')
    correction_notice_prefix = 'Measurement failed: '

    def __init__(self, window):
        super().__init__(window)
        self.window = window
        self.states = weakref.WeakKeyDictionary()
        self.jobs = []
        self.active = lambda: None
        self.summary_rows = SummaryRows(window.image_results_summary_dock)
        self.last_timings = {}
        self.batch_queue = []
        self.batch_active = []
        self.batch_managed = set()
        self.batch_limit = 2
        self.batch_timer = QtCore.QTimer(self)
        self.batch_timer.setInterval(75)
        self.batch_timer.timeout.connect(self._pump_batch_queue)

    def state(self, canvas):
        if canvas not in self.states:
            self.states[canvas] = SimpleNamespace(results={}, summary=IncrementalSummary(),
                scale=None, scale_version=-1, job=None, paused=set())
        return self.states[canvas]

    def bind(self, canvas):
        if self.active() is canvas:
            return
        self._clear_measurement_notice()
        self.active = weakref.ref(canvas) if canvas is not None else lambda: None
        self.window.measured_results_dock.bind_canvas(canvas)
        self.summary_rows.clear()
        if canvas is None:
            return
        state = self.state(canvas)
        # Tab navigation is a bulk projection, not a new scientific calculation.
        # Returning to an image resumes an explicitly cancelled bulk update.
        canvas._measurement_dirty.update(state.paused)
        state.paused.clear()
        dock = self.window.measured_results_dock
        state.project = [uid for uid in state.results if uid not in dock._rows]
        self._project(canvas, state)

    def _project(self, canvas, state):
        deadline = time.perf_counter() + .006
        while state.project and time.perf_counter() < deadline:
            uid = state.project.pop()
            shape = canvas._shape_by_id.get(uid)
            if (shape is not None and shape.visible
                    and state.results.get(uid) == (shape._measurement_revision, state.scale_version)
                    and state.scale_version == canvas._measurement_scale_version):
                self.window.measured_results_dock.update_result(shape)
        if state.project:
            reference = weakref.ref(canvas)
            QtCore.QTimer.singleShot(0, lambda: self._continue_project(reference, state))
        else:
            self.summary_rows.write(state.summary, set(state.summary.bins), set(state.summary.counts),
                                    canvas.image_size, state.scale)
            self.window.measured_results_dock.select_shapes(canvas.selected_shape)

    def _continue_project(self, reference, state):
        canvas = reference()
        if canvas is not None and self.active() is canvas and not sip.isdeleted(canvas) and self.states.get(canvas) is state:
            self._project(canvas, state)

    def refresh(self, canvas, scale, force=False, background=False):
        if self.active() is canvas:
            self._clear_measurement_notice()
        start = time.perf_counter()
        state = self.state(canvas)
        scale = dict(scale) if scale else None
        full = force or state.scale != scale or state.scale_version != canvas._measurement_scale_version
        if full:
            self._cancel(state)
            state.scale, state.scale_version = scale, canvas._measurement_scale_version
            state.paused.clear()
            canvas._measurement_dirty.update(canvas._shape_by_id)
            # Old unit/scale values must not remain visible as current results.
            state.results.clear()
            state.summary = IncrementalSummary()
            if self.active() is canvas:
                self.window.measured_results_dock.clear_tables()
                self.summary_rows.clear()
        removed = canvas._measurement_removed.copy()
        canvas._measurement_removed.clear()
        for uid in removed:
            self._remove(canvas, state, uid)
            state.paused.discard(uid)
        dirty = canvas._measurement_dirty.copy()
        canvas._measurement_dirty.clear()
        if not dirty:
            self.last_timings = dict(feature_ms=0., row_ms=0., summary_ms=0., lookup_ms=0., total_ms=(time.perf_counter()-start)*1000)
            return
        threshold = getattr(self.window, 'measurement_async_threshold', self.async_threshold)
        # Vertex counts are O(1); do not inspect coordinates to decide scheduling.
        # A small batch of complex polygons can exceed the frame budget too.
        bulk_cost = 0.
        if len(dirty) > 1 and math.isfinite(threshold):
            for uid in dirty:
                shape = canvas._shape_by_id.get(uid)
                if shape is not None and shape.visible:
                    bulk_cost += (.15 + .01*len(shape.pointslist)) if shape.shape_type == 'polygon' else .5
        if background or len(dirty) >= threshold or bulk_cost > 50.:
            # Replacing a large pending state cancels the old producer safely.
            if state.job is not None:
                dirty.update(state.job.remaining)
                self._cancel(state)
            self._start(canvas, state, dirty, force)
            return
        timings = dict(feature_ms=0., row_ms=0., summary_ms=0., lookup_ms=0.)
        for uid in dirty:
            t = time.perf_counter()
            shape = canvas._shape_by_id.get(uid)
            timings['lookup_ms'] += (time.perf_counter()-t)*1000
            if shape is None or not shape.visible:
                self._remove(canvas, state, uid)
                continue
            t = time.perf_counter()
            try:
                ensure_features(shape, scale, force)
                shape.measurement_error = None
            except Exception as exc:
                shape.feature_results = {}
                shape.measurement_error = str(exc)
                shape.unit = 'pixel' if shape.shape_type == 'point' else (scale or {}).get('unit', 'pixel')
                if self.active() is canvas:
                    self.window.statusBar().showMessage(self.correction_notice_prefix + str(exc), 5000)
            timings['feature_ms'] += (time.perf_counter()-t)*1000
            self._publish(canvas, state, shape, timings)
        timings['total_ms'] = (time.perf_counter()-start)*1000
        self.last_timings = timings

    def _publish(self, canvas, state, shape, timings=None, job=None):
        uid = shape._history_id
        state.results[uid] = (shape._measurement_revision, state.scale_version)
        state.paused.discard(uid)
        t = time.perf_counter()
        if self.active() is canvas:
            self.window.measured_results_dock.update_result(shape)
            if any(s is shape for s in canvas.selected_shape):
                self.window.measured_results_dock.select_shapes(canvas.selected_shape)
        if timings is not None:
            timings['row_ms'] += (time.perf_counter()-t)*1000
        t = time.perf_counter()
        feature_keys, count_keys = state.summary.update(uid, (shape.shape_type, shape.label, shape.feature_results))
        if self.active() is canvas:
            if job is None:
                self.summary_rows.write(state.summary, feature_keys, count_keys, canvas.image_size, state.scale)
            else:
                job.summary_features.update(feature_keys)
                job.summary_counts.update(count_keys)
        if timings is not None:
            timings['summary_ms'] += (time.perf_counter()-t)*1000

    def _remove(self, canvas, state, uid):
        state.results.pop(uid, None)
        state.paused.discard(uid)
        feature_keys, count_keys = state.summary.update(uid)
        if self.active() is canvas:
            self.window.measured_results_dock.remove_result(uid)
            self.summary_rows.write(state.summary, feature_keys, count_keys, canvas.image_size, state.scale)

    def _start(self, canvas, state, dirty, force):
        worker = BulkWorker(state.scale, self)
        progress = QtWidgets.QProgressDialog('Updating measurements...', 'Cancel', 0, len(dirty), self.window)
        progress.setWindowModality(QtCore.Qt.NonModal)
        progress.setMinimumDuration(500)
        progress.setAutoClose(False)
        progress.setAutoReset(False)
        if canvas in self.batch_managed:
            progress.setMinimumDuration(2147483647)
            progress.hide()
        job = SimpleNamespace(canvas=weakref.ref(canvas), state=state, worker=worker,
            pending=list(dirty), remaining=set(dirty), scale_version=state.scale_version,
            scale=state.scale, force=force, progress=progress, finished_input=False, completed=0,
            summary_features=set(), summary_counts=set(),
            timings=dict(feature_ms=0., row_ms=0., summary_ms=0., lookup_ms=0.),
            started=time.perf_counter())
        state.job = job
        self.jobs.append(job)
        progress.canceled.connect(lambda: self._pause(job))
        worker.start()
        QtCore.QTimer.singleShot(0, lambda: self._pump(job))

    def _pause(self, job):
        canvas = job.canvas()
        if (canvas is None or sip.isdeleted(canvas) or self.states.get(canvas) is not job.state
                or job.state.job is not job or job.worker.cancelled.is_set()):
            return
        unfinished = self._unfinished(job)
        if not unfinished:
            return
        job.worker.cancelled.set()
        job.state.paused.update(unfinished)
        if self.active() is canvas:
            self.window.statusBar().showMessage(self.cancelled_notice, 5000)

    def _clear_measurement_notice(self):
        status = self.window.statusBar()
        message = status.currentMessage()
        if message == self.cancelled_notice or message.startswith(self.correction_notice_prefix):
            status.clearMessage()

    def _unfinished(self, job):
        canvas = job.canvas()
        if canvas is None or sip.isdeleted(canvas):
            return set()
        return {uid for uid in job.remaining if (canvas._shape_by_id.get(uid) is not None
                and canvas._shape_by_id[uid].visible
                and job.state.results.get(uid) != (canvas._shape_by_id[uid]._measurement_revision, job.scale_version))}

    def _cancel(self, state):
        if state.job is not None:
            job = state.job
            canvas = job.canvas()
            if canvas is not None and not sip.isdeleted(canvas):
                self._flush_summary(job, canvas)
            job.worker.cancelled.set()
            state.job = None

    def _flush_summary(self, job, canvas):
        if (self.active() is canvas and
                (job.summary_features or job.summary_counts)):
            start = time.perf_counter()
            self.summary_rows.write(job.state.summary, job.summary_features, job.summary_counts,
                                    canvas.image_size, job.state.scale)
            job.timings['summary_ms'] += (time.perf_counter()-start)*1000
        job.summary_features.clear()
        job.summary_counts.clear()

    def _pump(self, job):
        canvas = job.canvas()
        valid = (canvas is not None and not sip.isdeleted(canvas)
                 and self.states.get(canvas) is job.state and job.state.job is job
                 and canvas._measurement_scale_version == job.scale_version)
        if not valid:
            job.worker.cancelled.set()
        deadline = time.perf_counter() + .006
        while valid and not job.worker.cancelled.is_set() and time.perf_counter() < deadline:
            try:
                result = job.worker.outputs.get_nowait()
            except queue.Empty:
                result = None
            if result is not None:
                uid, revision, features, unit, key, error = result
                shape = canvas._shape_by_id.get(uid)
                if (shape is not None and shape.visible and shape._measurement_revision == revision
                        and job.state.results.get(uid) != (revision, job.scale_version)):
                    shape.feature_results = features
                    shape.measurement_error = error
                    shape.unit = unit
                    shape._measurement_key = key
                    shape._measurement_scale = dict(job.scale) if job.scale else None
                    self._publish(canvas, job.state, shape, job.timings, job)
                    if error and self.active() is canvas:
                        self.window.statusBar().showMessage(self.correction_notice_prefix + error, 5000)
                job.remaining.discard(uid)
                job.completed += 1
            if job.pending and not job.worker.inputs.full():
                uid = job.pending.pop()
                shape = canvas._shape_by_id.get(uid)
                if (shape is None or not shape.visible
                        or job.state.results.get(uid) == (shape._measurement_revision, job.scale_version)):
                    if shape is None or not shape.visible:
                        self._remove(canvas, job.state, uid)
                    job.remaining.discard(uid)
                    job.completed += 1
                else:
                    snapshot = (uid, shape._measurement_revision, shape.shape_type, shape.label, shape.group_id,
                                tuple((p.x(), p.y()) for p in shape.pointslist))
                    scale = job.scale or {}
                    key = (snapshot[2], snapshot[3], snapshot[4], snapshot[5],
                           scale.get('scale', 1.), scale.get('unit', 'pixel'))
                    if not job.force and shape.feature_results and shape._measurement_key == key:
                        self._publish(canvas, job.state, shape, job.timings, job)
                        job.remaining.discard(uid)
                        job.completed += 1
                    else:
                        job.worker.inputs.put_nowait(snapshot)
            elif not job.pending and not job.finished_input and not job.worker.inputs.full():
                job.worker.inputs.put_nowait(None)
                job.finished_input = True
            elif result is None:
                break
        if valid:
            job.progress.setValue(job.completed)
        if not job.worker.isRunning() and (job.worker.cancelled.is_set() or job.worker.outputs.empty()):
            if valid:
                self._flush_summary(job, canvas)
                job.timings['total_ms'] = (time.perf_counter()-job.started)*1000
                self.last_timings = job.timings
            if valid and job.worker.cancelled.is_set():
                job.state.paused.update(self._unfinished(job))
            if job.state.job is job:
                job.state.job = None
            job.progress.blockSignals(True)
            job.progress.close()
            job.progress.deleteLater()
            job.worker.deleteLater()
            self.jobs.remove(job)
            return
        QtCore.QTimer.singleShot(1, lambda: self._pump(job))

    def release(self, canvas):
        self.batch_managed.discard(canvas)
        self.batch_queue = [tab for tab in self.batch_queue
                            if not sip.isdeleted(tab) and tab.property('graphics_view').canvas is not canvas]
        self.batch_active = [tab for tab in self.batch_active
                             if not sip.isdeleted(tab) and tab.property('graphics_view').canvas is not canvas]
        state = self.states.pop(canvas, None)
        if state is not None:
            self._cancel(state)
            state.results.clear()
            state.summary = IncrementalSummary()
        if self.active() is canvas:
            self.bind(None)
        self.window.measured_results_dock.release_projection(canvas)

    def cancel_all(self):
        self.cancel_batch()
        for job in self.jobs:
            job.worker.cancelled.set()

    def enqueue_batch_tab(self, tab):
        """Queue one tab's existing background Measurement with bounded concurrency."""
        if sip.isdeleted(tab) or self.window.tabWidget.indexOf(tab) < 0:
            return
        view = tab.property('graphics_view')
        if not view or not view.canvas or self.ready(view.canvas):
            return
        if tab not in self.batch_queue and tab not in self.batch_active:
            self.batch_queue.append(tab)
            self.batch_managed.add(view.canvas)
        self._pump_batch_queue()

    def _pump_batch_queue(self):
        retained = []
        for tab in self.batch_active:
            if sip.isdeleted(tab) or self.window.tabWidget.indexOf(tab) < 0:
                continue
            canvas = tab.property('graphics_view').canvas
            state = self.state(canvas)
            if state.job is None and canvas._measurement_dirty and not state.paused:
                self.start_tabs([tab])
            if self.ready(canvas) or (state.paused and state.job is None):
                self.batch_managed.discard(canvas)
            else:
                retained.append(tab)
        self.batch_active = retained
        while self.batch_queue and len(self.batch_active) < self.batch_limit:
            current = self.window.tabWidget.currentWidget()
            index = self.batch_queue.index(current) if current in self.batch_queue else 0
            tab = self.batch_queue.pop(index)
            if sip.isdeleted(tab) or self.window.tabWidget.indexOf(tab) < 0:
                continue
            canvas = tab.property('graphics_view').canvas
            if self.ready(canvas):
                self.batch_managed.discard(canvas)
                continue
            self.batch_active.append(tab)
            self.start_tabs([tab])
        if self.batch_queue or self.batch_active:
            self.batch_timer.start()
        else:
            self.batch_timer.stop()

    def cancel_batch(self):
        """Keep completed results and pause only pending batch measurements."""
        self.batch_timer.stop()
        for tab in self.batch_active:
            if not sip.isdeleted(tab) and self.window.tabWidget.indexOf(tab) >= 0:
                canvas = tab.property('graphics_view').canvas
                state = self.states.get(canvas)
                if state is not None and state.job is not None:
                    self._pause(state.job)
        self.batch_queue.clear()
        self.batch_active.clear()
        self.batch_managed.clear()

    def running(self):
        return bool(self.jobs)

    def ready(self, canvas):
        state = self.state(canvas)
        return (state.job is None and not state.paused and not canvas._measurement_dirty
                and getattr(state, 'batch_pending', None) is None
                and not getattr(state, 'project', ()))

    def start_tabs(self, tabs=None):
        """Submit batch-import measurements without waiting for jobs or report dismissal."""
        if getattr(self.window, '_closing_requested', False):
            return
        tabs = list(tabs) if tabs is not None else [self.window.tabWidget.widget(i)
                                                  for i in range(self.window.tabWidget.count())]
        timer = getattr(self.window, '_measurement_timer', None)
        if timer:
            timer.stop()
        for tab in tabs:
            if sip.isdeleted(tab) or self.window.tabWidget.indexOf(tab) < 0:
                continue
            view = tab.property('graphics_view')
            if not view or not view.canvas:
                continue
            canvas = view.canvas
            state = self.state(canvas)
            if self.ready(canvas):
                continue
            if self.active() is not canvas:
                state.project = []
            canvas._measurement_dirty.update(state.paused)
            state.paused.clear()
            self.refresh(canvas, resolve_scale(self.window, view), background=True)
            if getattr(state, 'batch_pending', None) is None:
                token = state.batch_pending = object()
                reference = weakref.ref(canvas)
                QtCore.QTimer.singleShot(0, lambda r=reference, s=state, t=token: self._finish_background_tab(r, s, t))

    def _background_tab_valid(self, reference, state, token):
        canvas = reference()
        if (sip.isdeleted(self.window) or getattr(self.window, '_closing_requested', False)
                or canvas is None or sip.isdeleted(canvas) or self.states.get(canvas) is not state
                or getattr(state, 'batch_pending', None) is not token):
            return None
        return canvas

    def _finish_background_tab(self, reference, state, token):
        canvas = self._background_tab_valid(reference, state, token)
        if canvas is None:
            return
        if state.paused:
            # Preserve explicit Measurement cancellation; closing Results never calls this.
            state.batch_pending = None
            return
        if canvas._measurement_dirty:
            self.refresh(canvas, state.scale, background=True)
        if state.job is not None:
            QtCore.QTimer.singleShot(10, lambda: self._finish_background_tab(reference, state, token))
            return
        self._warm_background_tab(reference, state, token, iter(list(state.results)))

    def _warm_background_tab(self, reference, state, token, pending):
        """Prepare inactive tables in GUI-thread slices before marking the tab ready."""
        canvas = self._background_tab_valid(reference, state, token)
        if canvas is None:
            return
        if state.job is not None or state.paused or canvas._measurement_dirty:
            self._finish_background_tab(reference, state, token)
            return
        dock = self.window.measured_results_dock
        original = dock._canvas_ref()
        dock.bind_canvas(canvas)
        dock._selecting = True
        deadline = time.perf_counter() + .006
        finished = False
        try:
            for uid in pending:
                shape = canvas._shape_by_id.get(uid)
                if (shape is not None and shape.visible
                        and state.results.get(uid) == (shape._measurement_revision, canvas._measurement_scale_version)):
                    values = (shape.unit, dict(shape.feature_results), shape.label, shape.group_id,
                              getattr(shape, 'measurement_error', None))
                    if dock._result_shapes.get(uid) is not shape or dock._result_states.get(uid) != values:
                        dock.update_result(shape)
                if time.perf_counter() >= deadline:
                    break
            else:
                finished = True
            if finished:
                for uid in set(dock._rows) - set(state.results):
                    dock.remove_result(uid)
        finally:
            dock._selecting = False
            dock.bind_canvas(original if original is None or not sip.isdeleted(original) else None)
        if finished:
            state.batch_pending = None
        else:
            QtCore.QTimer.singleShot(0, lambda: self._warm_background_tab(reference, state, token, pending))

    def refresh_tabs(self, tabs=None):
        """Finish only dirty measurements before a batch/scale action returns."""
        if getattr(self.window, '_closing_requested', False):
            return
        tabs = list(tabs) if tabs is not None else [self.window.tabWidget.widget(i)
                                                  for i in range(self.window.tabWidget.count())]
        progress = QtWidgets.QProgressDialog('Updating measurements…', '', 0, len(tabs), self.window)
        progress.setCancelButton(None)
        progress.setWindowModality(QtCore.Qt.WindowModal)
        progress.setMinimumDuration(500)
        timer = getattr(self.window, '_measurement_timer', None)
        if timer:
            timer.stop()
        try:
            for index, tab in enumerate(tabs):
                if sip.isdeleted(tab) or self.window.tabWidget.indexOf(tab) < 0:
                    continue
                view = tab.property('graphics_view')
                if not view or not view.canvas:
                    continue
                canvas = view.canvas
                state = self.state(canvas)
                if self.active() is not canvas:
                    state.project = []
                canvas._measurement_dirty.update(state.paused)
                state.paused.clear()
                self.refresh(canvas, resolve_scale(self.window, view))
                if state.job is not None:
                    state.job.progress.setCancelButton(None)
                    state.job.progress.setMinimumDuration(2147483647)
                    state.job.progress.hide()
                while not sip.isdeleted(canvas) and not self.ready(canvas):
                    if getattr(self.window, '_closing_requested', False):
                        return
                    QtWidgets.QApplication.processEvents()
                    if state.paused and state.job is None:
                        canvas._measurement_dirty.update(state.paused)
                        state.paused.clear()
                        self.refresh(canvas, resolve_scale(self.window, view))
                        if state.job is not None:
                            state.job.progress.setCancelButton(None)
                    time.sleep(.001)
                if not sip.isdeleted(canvas):
                    self.warm_projection(canvas, state)
                progress.setValue(index + 1)
                QtWidgets.QApplication.processEvents()
        finally:
            progress.close()
            progress.deleteLater()

    def warm_projection(self, canvas, state):
        """Build/update inactive table projections in responsive bounded slices."""
        dock = self.window.measured_results_dock
        original = dock._canvas_ref()
        pending = iter(list(state.results))
        while True:
            dock.bind_canvas(canvas)
            dock._selecting = True
            deadline = time.perf_counter() + .006
            finished = False
            try:
                for uid in pending:
                    shape = canvas._shape_by_id.get(uid)
                    if shape is not None and shape.visible:
                        values = (shape.unit, dict(shape.feature_results), shape.label, shape.group_id,
                                  getattr(shape, 'measurement_error', None))
                        if dock._result_shapes.get(uid) is not shape or dock._result_states.get(uid) != values:
                            dock.update_result(shape)
                    if time.perf_counter() >= deadline:
                        break
                else:
                    finished = True
                for uid in set(dock._rows) - set(state.results):
                    dock.remove_result(uid)
            finally:
                dock._selecting = False
                dock.bind_canvas(original if original is None or not sip.isdeleted(original) else None)
            if finished:
                return
            QtWidgets.QApplication.processEvents()
            if sip.isdeleted(canvas) or getattr(self.window, '_closing_requested', False):
                return
