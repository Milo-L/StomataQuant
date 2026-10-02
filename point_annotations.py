"""StomataQuant Point TXT: class_id normalized_x normalized_y (not YOLO pose)."""
import math
import re
from collections import Counter, defaultdict
from pathlib import Path

from PyQt5 import QtCore, QtWidgets, sip
from shape import Shape
from task_support import check_cancelled, OperationCancelled
from measurements import resolve_scale
from batch_ui import annotation_batch
from safe_io import source_suffix, write_unique_text_atomic


def image_dimensions(canvas):
    width, height = canvas.image_size.width(), canvas.image_size.height()
    if width <= 0 or height <= 0:
        raise ValueError('The original image dimensions must be positive.')
    return width, height


def class_id(value):
    # Classes are extensible in the existing editor; the color map is not a registry.
    if not re.fullmatch(r'[0-9]+', str(value)):
        raise ValueError(f'Invalid class ID: {value!r}; expected a non-negative integer.')
    return int(value)


def read_points(path, checkpoint=None):
    records = []
    with open(path, encoding='utf-8-sig') as file:
        for line_number, line in enumerate(file, 1):
            if checkpoint and line_number % 256 == 1:
                checkpoint()
            parts = line.split()
            if not parts:
                continue
            try:
                if len(parts) != 3:
                    raise ValueError('Expected exactly: class_id x y.')
                category = class_id(parts[0])
                x, y = float(parts[1]), float(parts[2])
                if not all(math.isfinite(v) and 0 <= v <= 1 for v in (x, y)):
                    raise ValueError('Coordinates must be finite and in [0, 1].')
                records.append((category, x, y))
            except ValueError as error:
                raise ValueError(f'{Path(path).name}, line {line_number}: {error}') from error
    if checkpoint:
        checkpoint()
    return records


def serialize_points(canvas, checkpoint=None):
    width, height = image_dimensions(canvas)
    original = list(canvas.shapes)
    lines = []
    for index, shape in enumerate(original):
        if checkpoint and index % 256 == 0:
            checkpoint()
        if shape.shape_type != 'point' or not shape.visible:
            continue
        if len(shape.pointslist) != 1:
            raise ValueError(f'Point {shape.group_id} must contain exactly one vertex.')
        category = class_id(shape.classnum)
        point = shape.pointslist[0]
        x, y = point.x() / width, point.y() / height
        if not all(math.isfinite(v) and 0 <= v <= 1 for v in (x, y)):
            raise ValueError(f'Point {shape.group_id}: coordinates are outside the original image or non-finite.')
        lines.append(f'{category} {x:.9f} {y:.9f}\n')
    if canvas.shapes != original:
        raise ValueError('Annotations changed during export. Please retry.')
    return ''.join(lines)


def write_points(path, canvas, checkpoint=None):
    data = serialize_points(canvas, checkpoint).encode('utf-8')
    if checkpoint:
        checkpoint()
    # Avoid destroying an existing file if validation or writing fails.
    output = QtCore.QSaveFile(str(path))
    if not output.open(QtCore.QIODevice.WriteOnly):
        raise OSError(output.errorString())
    try:
        if output.write(data) != len(data):
            raise OSError(output.errorString())
        if not output.commit():
            raise OSError(output.errorString())
    except Exception:
        output.cancelWriting()
        raise


def import_points(canvas, path, checkpoint=None, show_group_id=False, *, _records=None, replace=False):
    """Append native Points, matching the existing Annotation import semantics."""
    width, height = image_dimensions(canvas)
    records = read_points(path, checkpoint) if _records is None else _records
    original = list(canvas.shapes)
    retained = [] if replace else original
    labels = {}
    next_id = defaultdict(int)
    for shape in canvas.shapes:
        if shape.label:
            labels.setdefault(shape.classnum, shape.label)
    for shape in retained:
        if isinstance(shape.group_id, int):
            next_id[shape.classnum] = max(next_id[shape.classnum], shape.group_id + 1)
    added = []
    for index, (category, x, y) in enumerate(records):
        if checkpoint and index % 256 == 0:
            checkpoint()
        shape = Shape(label=labels.get(category, f'Class {category}'), classnum=category,
                      pointslist=[QtCore.QPointF(x * width, y * height)], shape_type='point',
                      group_id=next_id[category], scale_factor=canvas.scale_factor)
        next_id[category] += 1
        if show_group_id:
            shape.show_group_id()
        added.append(shape)
    if checkpoint:
        checkpoint()
    if canvas.shapes != original:
        raise ValueError('Annotations changed during import. Please retry.')
    if not added and len(retained) == len(canvas.shapes):
        return 0
    return commit_import(canvas, added, replace=replace, expected=original)


def commit_import(canvas, added, replace=False, expected=None):
    original = list(canvas.shapes)
    if expected is not None and original != expected:
        raise ValueError('Annotations changed during import. Please retry.')
    retained = [] if replace else original
    if not added and not (replace and original):
        return 0
    # Parse and build everything before the single undoable mutation.
    state_names = ('shapes', 'selected_shape', 'hovered_shape', '_last_hover_shape',
                   'hovered_point_index', 'mode', 'create_shape_type', 'current_shape', 'drawing',
                   'dragging_point', 'moving_shape', 'rotating', 'scaling_rotated_rectangle',
                   'rotating_shape', 'scaling_shape')
    old_state = {name: getattr(canvas, name, None) for name in state_names}
    old_selected = [(shape, shape.selected) for shape in original]
    old_undo = list(canvas.undo_stack)
    old_redo = list(canvas.redo_stack)
    old_pending = canvas._history_pending
    old_cache = canvas._history.cache
    canvas.save_state()
    blocked = canvas.blockSignals(True)
    try:
        for shape in canvas.shapes:
            shape.selected = False
        canvas.shapes = retained + added
        canvas.selected_shape = []
        canvas.hovered_shape = None
        canvas._last_hover_shape = None
        canvas.hovered_point_index = None
        canvas.set_mode('edit')
        canvas.drawing = False
        for name in ('dragging_point', 'moving_shape', 'rotating', 'scaling_rotated_rectangle'):
            setattr(canvas, name, False)
        for name in ('rotating_shape', 'scaling_shape'):
            setattr(canvas, name, None)
    except Exception:
        for name, value in old_state.items():
            setattr(canvas, name, value)
        for shape, selected in old_selected:
            shape.selected = selected
        canvas.undo_stack = old_undo
        canvas._history.redo = old_redo
        canvas._history_pending = old_pending
        canvas._history.cache = old_cache
        raise
    finally:
        canvas.blockSignals(blocked)
    canvas.update()
    canvas.shapeSelected.emit([])
    canvas.shapesChanged.emit()
    return len(added)


def require_target(window, tab, canvas=None):
    if tab is None or sip.isdeleted(tab) or window.tabWidget.indexOf(tab) < 0:
        raise ValueError('The target image has been closed.')
    view = tab.property('graphics_view')
    if view is None or (isinstance(view, sip.simplewrapper) and sip.isdeleted(view)) or not view.canvas or (canvas is not None and view.canvas is not canvas):
        raise ValueError('The target image canvas is no longer available.')
    return view.canvas


def refresh_point_import(window, tab):
    canvas = require_target(window, tab)
    if getattr(window, '_defer_batch_refresh', False):
        return
    if window.tabWidget.currentWidget() is tab:
        window.shapedockinstance.sync_shapes(canvas.shapes)
        window.labeldockinstance.sync_labels(canvas.shapes, Shape.get_color_by_classnum)
        window.actionEditShapes.setChecked(True)
        window.update_undo_button()
        window.update_actions_inToolBar()
        window.refresh_measurements()
        window._sync_shape_selection(canvas.selected_shape)


def import_checkpoint(window, tab, canvas, progress):
    QtWidgets.QApplication.processEvents()
    check_cancelled(lambda: progress.wasCanceled() or getattr(window, '_closing_requested', False))
    require_target(window, tab, canvas)


BATCH_PREFIX = 'Point_Annotation_Batch_Exported_by_StomataQuant_'
SINGLE_PREFIX = 'Point_Annotation_Exported_by_StomataQuant_'


def _choose_directory(window, title):
    return QtWidgets.QFileDialog.getExistingDirectory(
        window, title, '', QtWidgets.QFileDialog.ShowDirsOnly | QtWidgets.QFileDialog.DontResolveSymlinks)


def _batch_progress(window, action, count):
    progress = QtWidgets.QProgressDialog(f'{action}ing Point annotations...', 'Cancel', 0, count, window)
    progress.setWindowTitle(f'Batch {action} Progress')
    progress.setWindowModality(QtCore.Qt.WindowModal)
    progress.setMinimumDuration(0)
    return progress


def _finish_batch(window, progress, original_tab, results, action, directory):
    if not getattr(window, '_annotation_batch', None):
        window._batch_running = False
    progress.close()
    progress.deleteLater()
    if original_tab is not None and not sip.isdeleted(original_tab) and window.tabWidget.indexOf(original_tab) >= 0:
        window.tabWidget.setCurrentWidget(original_tab)
    window._last_point_batch_results = results
    if not getattr(window, '_closing_requested', False):
        report = f'Point Annotation Batch {action} Results:\n\n'
        report += '\n'.join(f'{key.replace("_", " ").title()}: {results[key]}' for key in
                            ('images', 'annotations', 'matched', 'success', 'missing', 'failed', 'canceled', 'empty')
                            if key in results)
        report += f'\n\nDirectory: {directory}'
        if results['errors']:
            report += '\n\n' + '\n'.join(results['errors'][:20])
        QtWidgets.QMessageBox.information(window, f'Batch {action} Complete', report)


@annotation_batch(restore_original=True)
def batch_points(window):
    """Export each open Canvas without switching tabs or modifying its annotations."""
    tabs = [window.tabWidget.widget(i) for i in range(window.tabWidget.count())]
    if not tabs:
        QtWidgets.QMessageBox.warning(window, 'Notice', 'No image tabs open. Please open some images first.')
        return
    directory = _choose_directory(window, 'Select Export Directory')
    if not directory:
        return
    directory = Path(directory) / 'StomataQuant Exported Point Annotations'
    directory.mkdir(parents=True, exist_ok=True)
    stems = {id(tab): Path(tab.property('file_path')).stem for tab in tabs}
    duplicates = Counter(stem.casefold() for stem in stems.values())
    progress = _batch_progress(window, 'Export', len(tabs))
    results = dict(success=0, missing=0, failed=0, canceled=0, empty=0, errors=[])
    original_tab = window.tabWidget.currentWidget()
    window._batch_running = True
    try:
        for index, tab in enumerate(tabs):
            progress.setValue(index)
            QtWidgets.QApplication.processEvents()
            if progress.wasCanceled() or getattr(window, '_closing_requested', False):
                results['canceled'] += len(tabs) - index
                break
            stem = stems[id(tab)]
            progress.setLabelText(f'Exporting {index + 1}/{len(tabs)}: {stem}')
            try:
                canvas = require_target(window, tab)
                source = tab.property('file_path')
                filename = BATCH_PREFIX + stem
                if duplicates[stem.casefold()] > 1:
                    filename += '__' + source_suffix(source)
                content = serialize_points(canvas,
                    lambda: import_checkpoint(window, tab, canvas, progress))
                import_checkpoint(window, tab, canvas, progress)
                if not content:
                    results['empty'] += 1
                    progress.setValue(index + 1)
                    continue
                write_unique_text_atomic(directory, filename + '.txt', source, content)
                results['success'] += 1
            except OperationCancelled:
                results['canceled'] += len(tabs) - index
                break
            except Exception as error:
                results['failed'] += 1
                results['errors'].append(f'{stem}: {error}')
            progress.setValue(index + 1)
    finally:
        _finish_batch(window, progress, original_tab, results, 'Export', directory)
    return results


@annotation_batch(importing=True, restore_original=True)
def batch_import_points(window, open_image):
    from annotation_matching import run_import
    from types import SimpleNamespace
    return run_import(SimpleNamespace(main_window=window, _open_image=open_image), 'point')
