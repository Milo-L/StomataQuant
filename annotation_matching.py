"""Editable batch pairing and explicit, transactional existing-Canvas imports."""
from collections import Counter
from difflib import SequenceMatcher
from pathlib import Path
from PyQt5 import QtCore, QtGui, QtWidgets, sip
from batch_ui import checkpoint, image_path_key
from safe_io import source_suffix
from task_support import OperationCancelled
from dialog_ui import ResponsiveDialog
from ImageGraphicsView import displayed_image_size


def annotation_is_empty(path, kind=None):
    """An existing blank file or header-only rectangle table has zero shapes."""
    from annotation_io import rectangle_table_header_index
    try:
        lines = Path(path).read_text(encoding='utf-8-sig').splitlines()
    except (OSError, UnicodeError):
        return False
    if not any(line.strip() for line in lines):
        return True
    if kind == 'rectangle':
        header = rectangle_table_header_index(lines)
        return header is not None and not any(line.strip() for line in lines[header + 1:])
    return False


def automatic_matches(images, annotations, kind):
    title = {'point': 'Point', 'polygon': 'Polygon', 'rectangle': 'Rectangle',
             'rotated_rectangle': 'Rotated_Rectangle'}[kind]
    prefixes = ('', title + '_Annotation_Exported_by_StomataQuant_',
                title + '_Annotation_Batch_Exported_by_StomataQuant_')
    counts = Counter(image.stem.casefold() for image in images)
    rows = []
    annotation_keys = {path: path.stem.casefold() for path in annotations}
    for image in images:
        hashed = {prefix + image.stem + '__' + source_suffix(str(image)) for prefix in prefixes[1:]}
        accepted = hashed if counts[image.stem.casefold()] > 1 else hashed | {prefix + image.stem for prefix in prefixes}
        matches = [path for path in annotations if annotation_keys[path] in {stem.casefold() for stem in accepted}]
        reason = 'Matched' if len(matches) == 1 else 'Missing annotation' if not matches and counts[image.stem.casefold()] == 1 else 'Ambiguous match'
        rows.append(dict(image=image, annotation=matches[0] if len(matches) == 1 else None,
                         candidates=matches, enabled=len(matches) == 1, reason=reason))
    # Exact ownership is decided first. Only unmatched, unique image stems may
    # use a conservative fuzzy match; never steal a known exact annotation.
    exact_owned = {row['annotation'] for row in rows if row['enabled']}
    for row in rows:
        if row['candidates'] or counts[row['image'].stem.casefold()] > 1:
            continue
        image_key = row['image'].stem.casefold()
        for suffix in ('_merged',):
            if image_key.endswith(suffix):
                image_key = image_key[:-len(suffix)]
                break
        ranked = []
        for path in annotations:
            if path in exact_owned:
                continue
            key = annotation_keys[path]
            for prefix in prefixes[1:]:
                if key.startswith(prefix.casefold()):
                    key = key[len(prefix):]
                    break
            for suffix in ('_stomata', '_annotation', '_labels'):
                if key.endswith(suffix):
                    key = key[:-len(suffix)]
                    break
            score = SequenceMatcher(None, image_key, key).ratio()
            if score >= .82:
                ranked.append((score, path))
        ranked.sort(key=lambda item: (-item[0], str(item[1]).casefold()))
        if ranked:
            row['candidates'] = [path for _, path in ranked]
            if len(ranked) == 1 or ranked[0][0] - ranked[1][0] >= .10:
                row.update(annotation=ranked[0][1], enabled=True, reason='Fuzzy match')
            else:
                row['reason'] = 'Ambiguous match'
    used = Counter(row['annotation'] for row in rows if row['enabled'])
    for row in rows:
        if used[row['annotation']] > 1:
            row.update(annotation=None, enabled=False, reason='Ambiguous match')
        row['empty'] = bool(row['annotation'] and annotation_is_empty(row['annotation'], kind))
    return rows


class AnnotationMatchDialog(ResponsiveDialog):
    def __init__(self, rows, annotations, window):
        super().__init__(window)
        self.setWindowTitle('Confirm image ↔ annotation matches')
        self.resize(1000, 520)
        self.rows = [dict(row) for row in rows]
        self.annotations = list(annotations)
        self.annotation_model = QtGui.QStandardItemModel(self)
        self.annotation_model.appendRow(QtGui.QStandardItem('Select annotation...'))
        for path in self.annotations:
            item = QtGui.QStandardItem(path.name)
            item.setData(str(path), QtCore.Qt.UserRole)
            item.setData(str(path), QtCore.Qt.ToolTipRole)
            self.annotation_model.appendRow(item)
        self.main_window = window
        layout = QtWidgets.QVBoxLayout(self)
        layout.addWidget(QtWidgets.QLabel('Review matches before importing. Choose an annotation, uncheck an image to skip it, or reorder selected rows.'))
        self.table = QtWidgets.QTableWidget(0, 4, self)
        self.table.setHorizontalHeaderLabels(['Import', 'Image', 'Annotation', 'Status'])
        self.table.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QtWidgets.QAbstractItemView.ExtendedSelection)
        self.table.horizontalHeader().setSectionResizeMode(1, QtWidgets.QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(2, QtWidgets.QHeaderView.Stretch)
        for column in (0, 3):
            self.table.horizontalHeader().setSectionResizeMode(column, QtWidgets.QHeaderView.ResizeToContents)
        layout.addWidget(self.table)
        buttons = QtWidgets.QHBoxLayout()
        for title, callback in [('Move Up', lambda: self.move(-1)), ('Move Down', lambda: self.move(1)),
                                ('Swap selected annotations', self.swap), ('Cancel selected items', self.cancel_selected)]:
            button = QtWidgets.QPushButton(title)
            button.clicked.connect(callback)
            buttons.addWidget(button)
        layout.addLayout(buttons)
        box = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel)
        box.button(box.Ok).setText('Confirm import')
        box.accepted.connect(self.accept)
        box.rejected.connect(self.reject)
        layout.addWidget(box)
        self.redraw()

    def redraw(self):
        self.table.setRowCount(len(self.rows))
        opened = {image_path_key(self.main_window.tabWidget.widget(i).property('file_path'))
                  for i in range(self.main_window.tabWidget.count())}
        for row, record in enumerate(self.rows):
            check = QtWidgets.QTableWidgetItem()
            check.setFlags(QtCore.Qt.ItemIsEnabled | QtCore.Qt.ItemIsUserCheckable)
            check.setCheckState(QtCore.Qt.Checked if record['enabled'] else QtCore.Qt.Unchecked)
            self.table.setItem(row, 0, check)
            image_item = QtWidgets.QTableWidgetItem(record['image'].name)
            image_item.setToolTip(str(record['image']))
            self.table.setItem(row, 1, image_item)
            combo = QtWidgets.QComboBox()
            combo.setModel(self.annotation_model)
            if record['annotation']:
                combo.setCurrentIndex(combo.findData(str(record['annotation'])))
            combo.activated.connect(lambda _, r=row: self.table.item(r, 0).setCheckState(QtCore.Qt.Checked))
            self.table.setCellWidget(row, 2, combo)
            status = record['reason'] + (' — empty annotation' if record.get('empty') else '')
            status += '; existing Canvas will be reused' if image_path_key(record['image']) in opened else ''
            status_item = QtWidgets.QTableWidgetItem(status)
            status_item.setToolTip(status)
            self.table.setItem(row, 3, status_item)

    def selections(self):
        return [dict(record, enabled=self.table.item(row, 0).checkState() == QtCore.Qt.Checked,
                     annotation=Path(self.table.cellWidget(row, 2).currentData())
                     if self.table.cellWidget(row, 2).currentData() else None)
                for row, record in enumerate(self.rows)]

    def move(self, direction):
        selected = sorted({index.row() for index in self.table.selectionModel().selectedRows()}, reverse=direction > 0)
        self.rows = self.selections()
        destinations = []
        for row in selected:
            target = row + direction
            if 0 <= target < len(self.rows):
                self.rows[row], self.rows[target] = self.rows[target], self.rows[row]
                destinations.append(target)
        self.redraw()
        self.table.clearSelection()
        for row in destinations:
            self.table.selectionModel().select(self.table.model().index(row, 1), QtCore.QItemSelectionModel.Select | QtCore.QItemSelectionModel.Rows)

    def swap(self):
        selected = sorted({index.row() for index in self.table.selectionModel().selectedRows()})
        if len(selected) != 2:
            QtWidgets.QMessageBox.warning(self, 'Pairing', 'Select exactly two image rows to swap annotations.')
            return
        self.rows = self.selections()
        a, b = [self.rows[row] for row in selected]
        a['annotation'], b['annotation'] = b['annotation'], a['annotation']
        self.redraw()

    def cancel_selected(self):
        for index in self.table.selectionModel().selectedRows():
            self.table.item(index.row(), 0).setCheckState(QtCore.Qt.Unchecked)

    def accept(self):
        rows = [record for record in self.selections() if record['enabled']]
        images = [image_path_key(record['image']) for record in rows]
        annotations = [image_path_key(record['annotation']) for record in rows]
        if any(record['annotation'] is None for record in rows) or len(images) != len(set(images)) or len(annotations) != len(set(annotations)):
            QtWidgets.QMessageBox.warning(self, 'Invalid pairing', 'Each enabled image requires one unique annotation. Resolve missing or duplicate pairings before importing.')
            return
        super().accept()


def choose_existing_import_action(window, path):
    box = QtWidgets.QMessageBox(window)
    box.setWindowTitle('Image already contains shapes')
    box.setText(str(path) + '\nChoose how to import annotations into the existing Canvas.')
    append = box.addButton('Append', QtWidgets.QMessageBox.AcceptRole)
    replace = box.addButton('Replace all existing shapes', QtWidgets.QMessageBox.DestructiveRole)
    cancel = box.addButton('Cancel', QtWidgets.QMessageBox.RejectRole)
    box.setDefaultButton(cancel)
    box.exec_()
    return 'append' if box.clickedButton() is append else 'replace' if box.clickedButton() is replace else 'cancel'


def run_import(owner, kind):
    from point_annotations import read_points, import_points, require_target, refresh_point_import
    from annotation_io import import_warning, require_annotation_text
    window = owner.main_window
    images = [Path(window.tabWidget.widget(i).property('file_path'))
              for i in range(window.tabWidget.count())]
    if not images:
        image_dir = QtWidgets.QFileDialog.getExistingDirectory(window, 'Select Image Directory')
        if not image_dir:
            return
        images = sorted((path for path in Path(image_dir).iterdir() if path.is_file() and path.suffix.lower() in ('.png', '.jpg', '.jpeg', '.bmp', '.tif', '.tiff')), key=lambda path: path.name.casefold())
    kind_title = {'point': 'Point', 'polygon': 'Polygon', 'rectangle': 'Rectangle',
                  'rotated_rectangle': 'Rotated Rectangle'}[kind]
    annotation_dir = QtWidgets.QFileDialog.getExistingDirectory(
        window, f'Select {kind_title} Annotation Folder')
    if not annotation_dir:
        return
    annotations = sorted((path for path in Path(annotation_dir).iterdir() if path.is_file() and path.suffix.lower() == '.txt'), key=lambda path: path.name.casefold())
    rows = automatic_matches(images, annotations, kind)
    dialog = AnnotationMatchDialog(rows, annotations, window)
    if dialog.exec_() != QtWidgets.QDialog.Accepted:
        return
    rows = dialog.selections()
    # Revalidate even when exec_ is supplied by an automation harness.
    enabled = [row for row in rows if row['enabled']]
    keys = [image_path_key(row['annotation']) for row in enabled]
    if None in keys or len(keys) != len(set(keys)):
        QtWidgets.QMessageBox.warning(window, 'Invalid pairing', 'Resolve missing or duplicate annotation pairings.')
        return
    results = dict(images=len(images), annotations=len(annotations), matched=0, success=0, failed=0,
                   missing=0, canceled=0, empty=0, errors=[], successful_files=[], failed_files=[],
                   skipped=[], imported_shapes=0)
    progress = QtWidgets.QProgressDialog('Importing annotations…', 'Cancel', 0, len(rows), window)
    progress.setMinimumDuration(0)
    progress.setWindowModality(QtCore.Qt.WindowModal)
    session = getattr(window, '_annotation_batch', None)
    if session:
        session.progress = progress
    used = set()
    try:
        for index, row in enumerate(rows):
            path, annotation = row['image'], row['annotation']
            try:
                checkpoint(window)
                if not row['enabled']:
                    category = 'missing' if row['reason'] == 'Missing annotation' and annotation is None else 'failed' if row['reason'] == 'Ambiguous match' and annotation is None else 'canceled'
                    results[category] += 1
                    if category != 'canceled':
                        results['errors'].append(f'{path}: {row["reason"]}')
                    continue
                results['matched'] += 1
                used.add(annotation)
                records = None
                if kind == 'point':
                    records = read_points(annotation, lambda: checkpoint(window))
                else:
                    size = displayed_image_size(path)
                    if size.width() <= 0 or size.height() <= 0:
                        raise ValueError('Image dimensions cannot be read.')
                    with annotation.open(encoding='utf-8-sig') as stream:
                        require_annotation_text(stream.readlines())
                checkpoint(window)
                tab_index = owner._open_image(str(path))
                if tab_index < 0:
                    raise ValueError('Image open failed.')
                tab = window.tabWidget.widget(tab_index)
                canvas = require_target(window, tab)
                if image_path_key(tab.property('file_path')) != image_path_key(path):
                    raise ValueError('Target image changed while opening.')
                mode = choose_existing_import_action(window, path) if canvas.shapes else 'append'
                if mode == 'cancel':
                    results['canceled'] += 1
                    continue
                if mode not in ('append', 'replace'):
                    raise ValueError('Invalid import action.')
                checkpoint(window, tab, canvas)
                if kind == 'point':
                    count = import_points(canvas, annotation, lambda: checkpoint(window, tab, canvas),
                                          getattr(window, '_global_show_group_id', False), _records=records, replace=mode == 'replace')
                else:
                    method = getattr(owner, '_import_' + kind + '_annotation')
                    if not method(window.tabWidget.indexOf(tab), str(annotation), replace=mode == 'replace'):
                        raise ValueError(owner.last_import_error or 'Annotation import failed.')
                    count = owner.last_import_count
                    results['skipped'].extend(
                        (number, f'{annotation.name}: {reason}')
                        for number, reason in owner.last_import_skipped)
                refresh_point_import(window, tab)
                window.measurement_controller.enqueue_batch_tab(tab)
                if session is not None:
                    session.pipelined_measurements = True
                results['success'] += 1
                results['imported_shapes'] += count
                results['empty'] += count == 0
                results['successful_files'].append((str(path), str(annotation)))
            except OperationCancelled:
                results['canceled'] += len(rows) - index
                break
            except Exception as error:
                results['failed'] += 1
                results['errors'].append(f'{path} ↔ {annotation}: {error}')
                results['failed_files'].append((str(path), str(annotation), str(error)))
            finally:
                progress.setValue(index + 1)
        results['unmatched_annotations'] = [str(path) for path in annotations if path not in used]
    finally:
        progress.close()
        owner.last_import_report = dict(successful=[annotation for _, annotation in results['successful_files']],
                                        failed=results['failed_files'], counts=results, errors=results['errors'])
        window._last_annotation_import_report = results
        if kind == 'point':
            window._last_point_batch_results = results
        if not getattr(window, '_closing_requested', False):
            if results['skipped']:
                QtWidgets.QMessageBox.warning(window, 'Annotation Import Warning',
                    import_warning(results['skipped'], results['imported_shapes']))
            if session is not None:
                # The decorator commits batch GUI state and starts measurements first.
                session.import_results = results
            else:
                from batch_ui import show_import_results
                for tab_index in range(window.tabWidget.count()):
                    window.measurement_controller.enqueue_batch_tab(window.tabWidget.widget(tab_index))
                show_import_results(window, results)
    return results
