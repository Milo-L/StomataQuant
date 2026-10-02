"""Full-fidelity annotation state used by the unsaved-tab guard."""
import json
import math
from pathlib import Path

from PyQt5.QtCore import QPointF

from safe_io import write_text_atomic, source_suffix
from shape import Shape
from geometry import require_valid_polygon


def session_path(image_path):
    source = Path(image_path)
    return source.parent / ('.sq-' + source_suffix(source) + '.json')


_COUNTS = {'point': 1, 'line': 2, 'rectangle': 2, 'rotated_rectangle': 4}


def _validate_shape(kind, points):
    if (kind not in (*_COUNTS, 'polygon') or
            (len(points) != _COUNTS[kind] if kind in _COUNTS else len(points) < 3)):
        raise ValueError('Invalid annotation shape in session.')
    if not all(len(pair) == 2 and all(math.isfinite(float(value)) for value in pair)
               for pair in points):
        raise ValueError('Invalid annotation coordinates in session.')
    if kind == 'polygon':
        require_valid_polygon([QPointF(x, y) for x, y in points])


def snapshot(canvas):
    """Only editable annotation data; measurement and view state are excluded."""
    return tuple((shape.shape_type, shape.label, shape.classnum, shape.group_id,
                  shape.visible,
                  tuple((point.x(), point.y()) for point in shape.pointslist))
                 for shape in canvas.shapes)


def save(path, canvas):
    width, height = canvas.image_size.width(), canvas.image_size.height()
    shapes = snapshot(canvas)
    for kind, label, category, group, visible, points in shapes:
        _validate_shape(kind, points)
    payload = {'version': 1, 'image_size': [width, height],
               'shapes': [dict(shape_type=kind, label=label, classnum=category,
                               group_id=group, visible=visible,
                               points=points)
                          for kind, label, category, group, visible, points in shapes]}
    write_text_atomic(path, json.dumps(payload, ensure_ascii=False, allow_nan=False, indent=2))
    return shapes


def load(path, canvas):
    payload = json.loads(Path(path).read_text(encoding='utf-8'))
    if payload.get('version') != 1:
        raise ValueError('Unsupported annotation session version.')
    size = [canvas.image_size.width(), canvas.image_size.height()]
    if payload.get('image_size') != size:
        raise ValueError('Annotation session image size differs from the opened image.')
    shapes = []
    for record in payload['shapes']:
        kind = record['shape_type']
        coords = record['points']
        _validate_shape(kind, coords)
        shape = Shape(label=record['label'], classnum=record['classnum'],
                      group_id=record['group_id'], shape_type=kind,
                      pointslist=[QPointF(*pair) for pair in coords])
        shape.visible = bool(record['visible'])
        shapes.append(shape)
    return shapes
