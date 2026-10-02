"""Open-folder and local-file drop routing through the existing annotation importers."""
import json
import threading
from collections import Counter, defaultdict
from pathlib import Path
from types import SimpleNamespace

from PyQt5 import QtCore, QtGui, QtWidgets, sip

from annotation_io import (parse_import_lines, import_warning, require_annotation_text,
                           rectangle_table_header_index)
from annotation_matching import AnnotationMatchDialog, automatic_matches, annotation_is_empty
from annotation_session import load as load_session, session_path
from batch_ui import image_path_key
from point_annotations import read_points, import_points, commit_import, require_target, refresh_point_import
from ImageGraphicsView import displayed_image_size


IMAGE_SUFFIXES = {'.png', '.jpg', '.jpeg', '.bmp', '.tif', '.tiff'}
KINDS = ('point', 'polygon', 'rectangle', 'rotated_rectangle', 'session')
KIND_NAMES = dict(point='Point', polygon='Polygon', rectangle='Rectangle',
                  rotated_rectangle='Rotated Rectangle', session='StomataQuant Session')


def _files(paths, cancelled=None):
    seen = set()
    for entry in paths:
        if cancelled and cancelled():
            return
        path = Path(entry)
        if path.is_dir():
            candidates = (p for p in path.rglob('*') if p.is_file())
        elif path.is_file():
            candidates = [path]
        else:
            candidates = []
        for candidate in candidates:
            if cancelled and cancelled():
                return
            key = image_path_key(candidate)
            if key not in seen:
                seen.add(key)
                yield candidate.resolve()


def detect_annotation(path, image_sizes=()):
    """Return types accepted by the real import validators, not by a suffix guess."""
    path = Path(path)
    if path.suffix.casefold() == '.json':
        try:
            payload = json.loads(path.read_text(encoding='utf-8'))
            width, height = payload['image_size']
            if width <= 0 or height <= 0:
                return ()
            load_session(path, SimpleNamespace(image_size=QtCore.QSize(width, height)))
            return ('session',)
        except (OSError, ValueError, TypeError, KeyError, IndexError, AttributeError):
            return ()
    if path.suffix.casefold() != '.txt':
        return ()
    try:
        lines = path.read_text(encoding='utf-8-sig').splitlines()
    except (OSError, UnicodeError):
        return ()
    if not any(line.strip() for line in lines):
        stem = path.stem.casefold()
        if stem.endswith('_stomata') or stem.startswith('rectangle_annotation_'):
            return ('rectangle',)
        for prefix, kind in (('point_annotation_', 'point'),
                             ('polygon_annotation_', 'polygon'),
                             ('rotated_rectangle_annotation_', 'rotated_rectangle')):
            if stem.startswith(prefix):
                return (kind,)
        return KINDS[:-1]  # Keep an untyped empty file visible for manual type choice.
    if rectangle_table_header_index(lines) is not None and not any(
            line.strip() for line in lines[rectangle_table_header_index(lines) + 1:]):
        return ('rectangle',)
    try:
        require_annotation_text(lines)
    except ValueError:
        return ()
    kinds = []
    try:
        read_points(path)
        kinds.append('point')
    except (OSError, UnicodeError, ValueError):
        pass
    for kind in ('polygon', 'rectangle', 'rotated_rectangle'):
        for size in image_sizes or (QtCore.QSize(1000, 1000),):
            try:
                valid, _skipped = parse_import_lines(lines, kind, size.width(), size.height())
                if valid:
                    kinds.append(kind)
                    break
            except (ValueError, IndexError, OverflowError):
                pass
    # Exported names are reliable type evidence when the content also validates.
    prefixes = {'Point_Annotation_': 'point', 'Polygon_Annotation_': 'polygon',
                'Rectangle_Annotation_': 'rectangle',
                'Rotated_Rectangle_Annotation_': 'rotated_rectangle'}
    for prefix, kind in prefixes.items():
        if path.stem.casefold().startswith(prefix.casefold()) and kind in kinds:
            return (kind,)
        if (not kinds and kind != 'point'
                and path.stem.casefold().startswith(prefix.casefold())):
            return (kind,)
    return tuple(kinds)


def scan_paths(paths, progress=None, cancelled=None, image_paths=()):
    images, annotations, unsupported, pending = [], {}, [], []
    for count, path in enumerate(_files(paths, cancelled), 1):
        if cancelled and cancelled():
            break
        if path.suffix.casefold() in IMAGE_SUFFIXES and QtGui.QImageReader(str(path)).canRead():
            images.append(path)
        else:
            pending.append(path)
        if progress:
            progress(count)
    sizes = [displayed_image_size(path) for path in list(images) + list(image_paths)]
    sizes = [size for size in sizes if size.isValid()]
    for path in pending:
        if cancelled and cancelled():
            break
        kinds = detect_annotation(path, sizes)
        if kinds:
            annotations[path] = kinds
        else:
            unsupported.append(path)
    return SimpleNamespace(images=images, annotations=annotations, unsupported=unsupported)


def automatic_drop_matches(images, annotation_types):
    """One image row, with exact matches before reliable fuzzy matches."""
    images = list(images)
    by_image = defaultdict(list)
    for kind in KINDS[:-1]:
        paths = [path for path, kinds in annotation_types.items() if kind in kinds]
        if paths:
            for row in automatic_matches(images, paths, kind):
                if row['enabled']:
                    by_image[image_path_key(row['image'])].append(
                        (0 if row['reason'] == 'Matched' else 1, row['annotation'], row['reason']))
                elif row['candidates']:
                    by_image[image_path_key(row['image'])].extend(
                        (2, path, 'Ambiguous match') for path in row['candidates'])
    for image in images:
        for annotation, kinds in annotation_types.items():
            if 'session' in kinds and annotation.name.casefold() == session_path(image).name.casefold():
                by_image[image_path_key(image)].append((0, annotation, 'Matched'))
    rows = []
    for image in images:
        choices = by_image[image_path_key(image)]
        best = min((rank for rank, _, _ in choices), default=None)
        matches = {path: reason for rank, path, reason in choices if rank == best}
        annotation = next(iter(matches)) if len(matches) == 1 else None
        kinds = annotation_types[annotation] if annotation else ()
        kind = kinds[0] if len(kinds) == 1 else None
        reason = ('Unmatched' if not choices else 'Ambiguous match' if annotation is None
                  else 'Ambiguous type' if kind is None else matches[annotation])
        rows.append(dict(image=image, annotation=annotation, kind=kind,
                         enabled=annotation is not None and kind is not None,
                         reason=reason, empty=bool(annotation and
                             annotation_is_empty(annotation, kind))))
    used = Counter(row['annotation'] for row in rows if row['enabled'])
    for row in rows:
        if row['annotation'] is not None and used[row['annotation']] > 1:
            row.update(annotation=None, kind=None, enabled=False,
                       reason='Ambiguous match', empty=False)
    return rows


class DropAnnotationMatchDialog(AnnotationMatchDialog):
    """The existing editable matching table with one extra annotation-type column."""

    def __init__(self, rows, annotation_types, window, available_images=None):
        self.annotation_types = annotation_types
        super().__init__(rows, annotation_types, window)

    def redraw(self):
        self.table.setColumnCount(4)
        super().redraw()
        self.table.insertColumn(3)
        self.table.setHorizontalHeaderLabels(
            ['Import', 'Image / Tab', 'Annotation File', 'Annotation Type', 'Match Status'])
        self.table.horizontalHeader().setSectionResizeMode(3, QtWidgets.QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(4, QtWidgets.QHeaderView.ResizeToContents)
        for row, record in enumerate(self.rows):
            kind_box = QtWidgets.QComboBox(self.table)
            kind_box.addItem('Select type…', None)
            self.table.setCellWidget(row, 3, kind_box)
            self._update_types(row, record.get('kind'))
            annotation_box = self.table.cellWidget(row, 2)
            annotation_box.currentIndexChanged.connect(lambda _, r=row: self._update_types(r))
            kind_box.currentIndexChanged.connect(lambda _, r=row: self._type_changed(r))

    def _update_types(self, row, preferred=None):
        annotation_box = self.table.cellWidget(row, 2)
        kind_box = self.table.cellWidget(row, 3)
        path = Path(annotation_box.currentData()) if annotation_box.currentData() else None
        kinds = self.annotation_types.get(path, ())
        kind_box.blockSignals(True)
        kind_box.clear()
        kind_box.addItem('Select type…', None)
        for kind in kinds:
            kind_box.addItem(KIND_NAMES[kind], kind)
        selected = preferred if preferred in kinds else kinds[0] if len(kinds) == 1 else None
        kind_box.setCurrentIndex(kind_box.findData(selected))
        kind_box.blockSignals(False)
        if path:
            if path != self.rows[row]['annotation'] or self.rows[row]['reason'] not in ('Matched', 'Fuzzy match'):
                self.table.item(row, 4).setText('Manual match' if selected else 'Ambiguous type')
            if selected:
                self.table.item(row, 0).setCheckState(QtCore.Qt.Checked)

    def _type_changed(self, row):
        if self.table.cellWidget(row, 3).currentData():
            self.table.item(row, 0).setCheckState(QtCore.Qt.Checked)

    def selections(self):
        rows = super().selections()
        for row, record in enumerate(rows):
            record['kind'] = self.table.cellWidget(row, 3).currentData()
        return rows

    def accept(self):
        rows = [record for record in self.selections() if record['enabled']]
        annotations = [image_path_key(record['annotation']) for record in rows]
        if (any(not record['kind'] or not record['annotation'] for record in rows)
                or len(annotations) != len(set(annotations))):
            QtWidgets.QMessageBox.warning(self, 'Invalid pairing',
                'Choose an annotation and type for each enabled image, without reusing a file.')
            return
        QtWidgets.QDialog.accept(self)


def _choose_image_open(window, count, ignored):
    if window._open_dropped_images_for_session:
        return True
    box = QtWidgets.QMessageBox(window)
    box.setWindowTitle('Open dropped images')
    box.setText(f'Detected {count} images. Open them?')
    box.setInformativeText(f'{ignored} unsupported files will be ignored.')
    box.setStandardButtons(QtWidgets.QMessageBox.Open | QtWidgets.QMessageBox.Cancel)
    box.setDefaultButton(QtWidgets.QMessageBox.Open)
    checkbox = QtWidgets.QCheckBox("Don't ask again for this session", box)
    box.setCheckBox(checkbox)
    answer = box.exec_()
    if answer == QtWidgets.QMessageBox.Open and checkbox.isChecked():
        window._open_dropped_images_for_session = True
    return answer == QtWidgets.QMessageBox.Open


def _choose_annotation_mode(window, annotation=None, tab=None, batch=False):
    if window._drop_annotation_mode_for_session in ('append', 'replace'):
        return window._drop_annotation_mode_for_session
    box = QtWidgets.QMessageBox(window)
    box.setWindowTitle('Import Annotation')
    box.setText(('Matched annotations detected.' if batch else
                 f'Annotation file detected: {Path(annotation).name}\n'
                 f'Import into: {Path(tab.property("file_path")).name}'))
    append = box.addButton('Append', QtWidgets.QMessageBox.AcceptRole)
    replace = box.addButton('Replace', QtWidgets.QMessageBox.DestructiveRole)
    cancel = box.addButton('Cancel', QtWidgets.QMessageBox.RejectRole)
    box.setDefaultButton(cancel)
    checkbox = QtWidgets.QCheckBox("Don't ask again for this session", box)
    box.setCheckBox(checkbox)
    box.exec_()
    clicked = box.clickedButton()
    mode = 'append' if clicked is append else 'replace' if clicked is replace else 'cancel'
    if mode != 'cancel' and checkbox.isChecked():
        window._drop_annotation_mode_for_session = mode
    return mode


def _validated_import(window, tab, path, kind, mode):
    from BatchProcessor import BatchImporter
    canvas = require_target(window, tab)
    if kind == 'point':
        records = read_points(path)
        return import_points(canvas, path, show_group_id=window._global_show_group_id,
                             _records=records, replace=mode == 'replace'), []
    if kind == 'session':
        shapes = load_session(path, canvas)
        return commit_import(canvas, shapes, replace=mode == 'replace', expected=list(canvas.shapes)), []
    importer = BatchImporter(window)
    index = window.tabWidget.indexOf(tab)
    if not importer._import_annotation(index, str(path), kind, replace=mode == 'replace'):
        raise ValueError(importer.last_import_error or 'Annotation import failed.')
    return importer.last_import_count, importer.last_import_skipped


def _preflight(window, tab, path, kind):
    canvas = require_target(window, tab)
    if kind == 'point':
        read_points(path)
    elif kind == 'session':
        load_session(path, canvas)
    else:
        with Path(path).open(encoding='utf-8-sig') as stream:
            require_annotation_text(stream.readlines())


def _restore(canvas, state):
    canvas.shapes = state.shapes
    for shape, selected in state.selected_flags:
        shape.selected = selected
    for name, value in state.ui.items():
        setattr(canvas, name, value)
    canvas.undo_stack = state.undo
    canvas._history.redo = state.redo
    canvas._history.cache = state.cache
    canvas._history_pending = state.pending
    canvas.update()
    canvas.shapesChanged.emit()


def import_matches(window, rows, mode, background=False):
    """Preflight all files and roll back all affected Canvases if any import fails."""
    tab_by_key = {image_path_key(window.tabWidget.widget(i).property('file_path')):
                  window.tabWidget.widget(i) for i in range(window.tabWidget.count())}
    targets = []
    for row in rows:
        if not row['enabled']:
            continue
        tab = tab_by_key.get(image_path_key(row['image']))
        if tab is None or row['annotation'] is None or row.get('kind') not in KINDS:
            raise ValueError('An annotation match no longer has a valid target or type.')
        targets.append((tab, Path(row['annotation']), row['kind']))
    if not targets:
        return 0
    annotation_keys = [image_path_key(path) for _, path, _ in targets]
    if len(annotation_keys) != len(set(annotation_keys)):
        raise ValueError('Each annotation file may be imported only once per batch.')
    for tab, path, kind in targets:
        _preflight(window, tab, path, kind)
    originals = {}
    state_names = ('selected_shape', 'hovered_shape', '_last_hover_shape',
                   'hovered_point_index', 'mode', 'create_shape_type', 'current_shape',
                   'drawing', 'dragging_point', 'moving_shape', 'rotating',
                   'scaling_rotated_rectangle', 'rotating_shape', 'scaling_shape')
    for tab, _, _ in targets:
        canvas = require_target(window, tab)
        if canvas not in originals:
            originals[canvas] = SimpleNamespace(shapes=list(canvas.shapes),
                selected_flags=[(shape, shape.selected) for shape in canvas.shapes],
                ui={name: (list(canvas.selected_shape) if name == 'selected_shape'
                           else getattr(canvas, name, None)) for name in state_names},
                undo=list(canvas.undo_stack),
                redo=list(canvas.redo_stack), cache=dict(canvas._history.cache),
                pending=canvas._history_pending)
    old_defer = getattr(window, '_defer_batch_refresh', False)
    window._defer_batch_refresh = True
    imported = 0
    skipped = []
    try:
        replaced = set()
        for tab, path, kind in targets:
            effective_mode = ('append' if mode == 'replace' and tab in replaced else mode)
            count, rejected = _validated_import(window, tab, path, kind, effective_mode)
            imported += count
            skipped.extend((number, f'{path.name}: {reason}')
                           for number, reason in rejected)
            replaced.add(tab)
    except Exception:
        for canvas, state in originals.items():
            _restore(canvas, state)
        raise
    finally:
        window._defer_batch_refresh = old_defer
        if not old_defer:
            window.update_list_on_tab_changed(window.tabWidget.currentIndex())
            window.update_undo_button()
            if background:
                for tab, _, _ in targets:
                    window.measurement_controller.enqueue_batch_tab(tab)
            else:
                window.measurement_controller.refresh_tabs()
    if skipped:
        QtWidgets.QMessageBox.warning(window, 'Annotation Import Warning',
                                      import_warning(skipped, imported))
    return imported


def handle_drop(window, paths, target_tab=None):
    scan = scan_paths(paths, image_paths=[window.tabWidget.widget(i).property('file_path')
                                          for i in range(window.tabWidget.count())])
    window._last_drop_scan = scan
    if scan.images and _choose_image_open(window, len(scan.images), len(scan.unsupported)):
        window.open_image_paths(scan.images)
    if not scan.annotations:
        return scan
    tabs = [window.tabWidget.widget(i) for i in range(window.tabWidget.count())]
    if not tabs:
        QtWidgets.QMessageBox.warning(window, 'Import Annotation',
                                      'Open an image before importing annotations.')
        return scan
    try:
        if len(scan.annotations) == 1 and len(paths) == 1 and Path(paths[0]).is_file():
            path, kinds = next(iter(scan.annotations.items()))
            tab = target_tab if target_tab in tabs else window.tabWidget.currentWidget()
            if len(kinds) == 1:
                kind = kinds[0]
            else:
                names = [KIND_NAMES[kind] for kind in kinds]
                chosen, accepted = QtWidgets.QInputDialog.getItem(
                    window, 'Annotation type', f'Choose the type of {path.name}:', names, 0, False)
                if not accepted:
                    return scan
                kind = kinds[names.index(chosen)]
            mode = _choose_annotation_mode(window, path, tab)
            if mode != 'cancel':
                import_matches(window, [dict(image=Path(tab.property('file_path')),
                                             annotation=path, kind=kind, enabled=True)], mode)
            return scan
        images = [Path(tab.property('file_path')) for tab in tabs]
        rows = automatic_drop_matches(images, scan.annotations)
        dialog = DropAnnotationMatchDialog(rows, scan.annotations, window)
        if dialog.exec_() != QtWidgets.QDialog.Accepted:
            return scan
        selections = dialog.selections()
        if not any(row['enabled'] for row in selections):
            return scan
        mode = _choose_annotation_mode(window, batch=True)
        if mode != 'cancel':
            import_matches(window, selections, mode)
    except Exception as error:
        QtWidgets.QMessageBox.critical(window, 'Annotation import failed', str(error))
    return scan


_SCAN_WORKERS = set()


class ScanWorker(QtCore.QThread):
    progress = QtCore.pyqtSignal(int)
    scanned = QtCore.pyqtSignal(object)
    failed = QtCore.pyqtSignal(str)

    def __init__(self, paths, image_paths=()):
        super().__init__()
        self.paths = list(paths)
        self.image_paths = list(image_paths)
        self.cancelled = threading.Event()

    def run(self):
        try:
            result = scan_paths(self.paths,
                                lambda count: self.progress.emit(count) if count == 1 or count % 32 == 0 else None,
                                self.cancelled.is_set, self.image_paths)
        except Exception as error:
            self.failed.emit(str(error))
        else:
            self.progress.emit(len(result.images) + len(result.annotations) + len(result.unsupported))
            self.scanned.emit(result)


class DropBatchJob(QtCore.QObject):
    """Background classification followed by one GUI-thread tab/import step per event turn."""

    def __init__(self, window, paths, target_tab=None, folder=False):
        super().__init__(window)
        self.window, self.paths, self.target_tab, self.folder = window, list(paths), target_tab, folder
        self.done = self.cancelled = False
        self.scan_count = self.opened = self.imported = 0
        self.groups = []
        self.group_index = 0
        self.stage = 'open'
        self.measuring = {}
        self.measured = set()
        self.errors = []
        self.progress = QtWidgets.QProgressDialog('Scanning files: 0', 'Cancel', 0, 0, window)
        self.progress.setWindowTitle('Processing dropped files' if not folder else 'Opening folder')
        self.progress.setWindowModality(QtCore.Qt.NonModal)
        self.progress.setMinimumDuration(0)
        self.progress.setAutoClose(False)
        self.progress.setAutoReset(False)
        self.progress.canceled.connect(self.cancel)
        self.worker = ScanWorker(paths, [window.tabWidget.widget(i).property('file_path')
                                         for i in range(window.tabWidget.count())])
        _SCAN_WORKERS.add(self.worker)
        self.worker.finished.connect(lambda w=self.worker: _SCAN_WORKERS.discard(w))
        self.worker.progress.connect(self._scan_progress)
        self.worker.scanned.connect(self._scanned)
        self.worker.failed.connect(self._scan_failed)

    def start(self):
        self.progress.show()
        self.worker.start()

    def cancel(self):
        if self.done:
            return
        self.cancelled = True
        self.worker.cancelled.set()
        self.window.measurement_controller.cancel_batch()
        if not self.worker.isRunning():
            self._finish()

    def _scan_progress(self, count):
        if not self.done:
            self.scan_count = count
            self.progress.setLabelText(f'Scanning files: {count}')

    def _scan_failed(self, error):
        if not self.done:
            self.errors.append(f'Scanning files: {error}')
            self._finish()

    def _scanned(self, scan):
        if self.done:
            return
        if self.cancelled:
            self._finish()
            return
        self.scan = scan
        self.window._last_drop_scan = scan
        if self.folder:
            ignored = len(scan.unsupported) + len(scan.annotations)
            answer = QtWidgets.QMessageBox.question(self.window, 'Open Folder',
                f'Found {len(scan.images)} images. {ignored} unsupported files will be ignored. Open these images?',
                QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No, QtWidgets.QMessageBox.Yes)
            approved = answer == QtWidgets.QMessageBox.Yes
        else:
            approved = bool(scan.images and _choose_image_open(
                self.window, len(scan.images), len(scan.unsupported)))
        to_open = scan.images if approved else []
        existing = {image_path_key(self.window.tabWidget.widget(i).property('file_path')):
                    self.window.tabWidget.widget(i) for i in range(self.window.tabWidget.count())}
        prospective = [Path(tab.property('file_path')) for tab in existing.values()]
        prospective += [path for path in to_open if image_path_key(path) not in existing]
        selected = []
        if scan.annotations and not self.folder:
            if not prospective:
                QtWidgets.QMessageBox.warning(self.window, 'Import Annotation',
                                              'Open an image before importing annotations.')
            elif len(scan.annotations) == 1 and len(self.paths) == 1 and Path(self.paths[0]).is_file():
                path, kinds = next(iter(scan.annotations.items()))
                tab = self.target_tab if self.target_tab in existing.values() else self.window.tabWidget.currentWidget()
                if len(kinds) == 1:
                    kind = kinds[0]
                else:
                    names = [KIND_NAMES[kind] for kind in kinds]
                    chosen, accepted = QtWidgets.QInputDialog.getItem(
                        self.window, 'Annotation type', f'Choose the type of {path.name}:', names, 0, False)
                    if not accepted:
                        self._finish()
                        return
                    kind = kinds[names.index(chosen)]
                mode = _choose_annotation_mode(self.window, path, tab)
                if mode != 'cancel':
                    selected = [dict(image=Path(tab.property('file_path')), annotation=path,
                                     kind=kind, enabled=True)]
                    self.mode = mode
            else:
                rows = automatic_drop_matches(prospective, scan.annotations)
                dialog = DropAnnotationMatchDialog(rows, scan.annotations, self.window, prospective)
                if dialog.exec_() == QtWidgets.QDialog.Accepted:
                    selected = [row for row in dialog.selections() if row['enabled']]
                    if selected:
                        self.mode = _choose_annotation_mode(self.window, batch=True)
                        if self.mode == 'cancel':
                            selected = []
        if self.cancelled:
            self._finish()
            return
        new = [path for path in to_open if image_path_key(path) not in existing]
        grouped = defaultdict(list)
        for row in selected:
            grouped[image_path_key(row['image'])].append(row)
        ordered = list(new)
        ordered += [Path(tab.property('file_path')) for tab in existing.values()
                    if image_path_key(tab.property('file_path')) in grouped]
        self.groups = [(path, image_path_key(path) not in existing, grouped[image_path_key(path)])
                       for path in ordered]
        self.open_total = len(new)
        self.import_total = sum(len(rows) for _, _, rows in self.groups)
        self.measure_total = len(self.groups)
        self.total = self.open_total + self.import_total + self.measure_total
        if not self.groups:
            self._finish()
            return
        self.progress.setRange(0, max(self.total, 1))
        self.window._drop_batch_background = True
        QtCore.QTimer.singleShot(0, self._tick)

    def _tab_for(self, path):
        key = image_path_key(path)
        for index in range(self.window.tabWidget.count()):
            tab = self.window.tabWidget.widget(index)
            if image_path_key(tab.property('file_path')) == key:
                return tab
        return None

    def _advance(self):
        self.group_index += 1
        self.stage = 'open'
        QtCore.QTimer.singleShot(1, self._tick)

    def _update(self, message):
        completed = self.opened + self.imported + len(self.measured)
        self.progress.setLabelText(f'Processing {completed} / {self.total}\n{message}')
        self.progress.setValue(completed)

    def _tick(self):
        if self.done:
            return
        if self.cancelled:
            self._finish()
            return
        self._poll_measurements()
        if self.group_index >= len(self.groups):
            if len(self.measured) >= self.measure_total:
                self._finish()
            else:
                active_jobs = [self.window.measurement_controller.state(
                    tab.property('graphics_view').canvas).job
                    for tab in self.measuring.values() if not sip.isdeleted(tab)
                    and self.window.tabWidget.indexOf(tab) >= 0]
                active_jobs = [job for job in active_jobs if job is not None]
                shape_progress = (f'; shapes {sum(job.completed for job in active_jobs)} / '
                                  f'{sum(job.progress.maximum() for job in active_jobs)}'
                                  if active_jobs else '')
                self._update(f'Measuring: {len(self.measured)} / {self.measure_total}{shape_progress}')
                QtCore.QTimer.singleShot(75, self._tick)
            return
        path, needs_open, rows = self.groups[self.group_index]
        if self.stage == 'open':
            self.stage = 'import'
            if needs_open:
                self._update(f'Opening images: {self.opened + 1} / {self.open_total}')
                prior = getattr(self.window, '_defer_batch_refresh', False)
                old_suppress = getattr(self.window, '_suppress_automatic_session_load', False)
                active_before = self.window.tabWidget.currentWidget()
                self.window._defer_batch_refresh = True
                self.window._suppress_automatic_session_load = any(
                    'session' in kinds and image_path_key(annotation) == image_path_key(session_path(path))
                    for annotation, kinds in self.scan.annotations.items())
                try:
                    if not self.window.open_image_paths([path]):
                        self.errors.append(f'{path}: image could not be opened')
                    if (self.open_total > 1 and active_before is not None
                            and self.window.tabWidget.indexOf(active_before) >= 0):
                        self.window.tabWidget.setCurrentWidget(active_before)
                except Exception as error:
                    self.errors.append(f'{path}: {error}')
                finally:
                    self.window._defer_batch_refresh = prior
                    self.window._suppress_automatic_session_load = old_suppress
                self.opened += 1
            QtCore.QTimer.singleShot(1, self._tick)
            return
        tab = self._tab_for(path)
        if tab is None:
            self.measured.add(image_path_key(path))
            self.imported += len(rows)
            self._advance()
            return
        canvas = tab.property('graphics_view').canvas
        self.window.measurement_controller.batch_managed.add(canvas)
        if self.stage == 'import':
            self.stage = 'measure'
            if rows:
                self._update(f'Importing annotations: {self.imported + 1} / {self.import_total}')
                prior = getattr(self.window, '_defer_batch_refresh', False)
                self.window._defer_batch_refresh = True
                try:
                    import_matches(self.window, rows, self.mode, background=True)
                except Exception as error:
                    self.errors.append(f'{path}: {error}')
                finally:
                    self.window._defer_batch_refresh = prior
                self.imported += len(rows)
            QtCore.QTimer.singleShot(1, self._tick)
            return
        if self.window.tabWidget.currentWidget() is tab:
            prior = getattr(self.window, '_defer_batch_refresh', False)
            self.window._defer_batch_refresh = True
            try:
                self.window.update_list_on_tab_changed(self.window.tabWidget.currentIndex())
                self.window.update_undo_button()
            finally:
                self.window._defer_batch_refresh = prior
        self.window.measurement_controller.enqueue_batch_tab(tab)
        self.measuring[image_path_key(path)] = tab
        self._advance()

    def _poll_measurements(self):
        for key, tab in list(self.measuring.items()):
            if (sip.isdeleted(tab) or self.window.tabWidget.indexOf(tab) < 0 or
                    self.window.measurement_controller.ready(tab.property('graphics_view').canvas)):
                self.measured.add(key)
                self.measuring.pop(key, None)

    def _finish(self):
        if self.done:
            return
        self.done = True
        self.window._drop_batch_background = False
        for path, _, _ in self.groups:
            tab = self._tab_for(path)
            if tab is not None:
                self.window.measurement_controller.batch_managed.discard(
                    tab.property('graphics_view').canvas)
        if getattr(self.window, '_drop_batch', None) is self:
            self.window._drop_batch = None
        if self.errors:
            self.window.statusBar().showMessage(
                f'{len(self.errors)} file(s) could not be processed. {self.errors[0]}', 10000)
        self.progress.close()
        self.progress.deleteLater()
        self.deleteLater()


def start_drop(window, paths, target_tab=None, folder=False):
    current = getattr(window, '_drop_batch', None)
    if current is not None and not current.done:
        current.progress.raise_()
        current.progress.activateWindow()
        return current
    job = DropBatchJob(window, paths, target_tab, folder)
    window._drop_batch = job
    job.start()
    return job
