"""YOLO annotation parsing and strict export validation."""
import math
import re
import numpy as np
from PyQt5.QtCore import QPointF
from shapely.geometry import Polygon, box
from geometry import require_valid_polygon, minimum_rectangle_size, rectangle_side_lengths


_RECTANGLE_TABLE_HEADER = ('x1', 'y1', 'x2', 'y2', 'center_x', 'center_y',
                           'confidence', 'class_id', 'class_name')


def rectangle_table_header_index(lines):
    """Recognize the pixel table only by its complete, explicit header."""
    for index, line in enumerate(lines):
        if line.strip():
            fields = tuple(re.split(r'[,\s]+', line.strip().lower()))
            return index if fields == _RECTANGLE_TABLE_HEADER else None
    return None


def parse_rectangle_table_line(line, width, height):
    fields = re.split(r'[,\s]+', line.strip())
    if len(fields) != len(_RECTANGLE_TABLE_HEADER):
        raise ValueError('Rectangle table requires nine fields')
    x1, y1, x2, y2, center_x, center_y, confidence = map(float, fields[:7])
    if not all(math.isfinite(value) for value in
               (x1, y1, x2, y2, center_x, center_y, confidence)):
        raise ValueError('Non-finite rectangle table value')
    classnum = int(fields[7])
    if classnum < 0:
        raise ValueError('Class ID must be a non-negative integer')
    label = fields[8]
    if not label:
        raise ValueError('Class name is empty')
    minimum = minimum_rectangle_size(width, height)
    if x2 - x1 < minimum or y2 - y1 < minimum:
        raise ValueError('Rectangle width and height are too small')
    points = [QPointF(x1, y1), QPointF(x2, y2)]
    if not shape_intersects_image(points, 'rectangle', width, height):
        raise ValueError('Shape lies completely outside the image bounds.')
    return classnum, points, label


def shape_intersects_image(points, kind, width, height):
    """Test the actual shape against the closed image rectangle, without clipping it."""
    image = box(0, 0, width, height)
    if kind == 'rectangle':
        x1, x2 = sorted((points[0].x(), points[1].x()))
        y1, y2 = sorted((points[0].y(), points[1].y()))
        shape = box(x1, y1, x2, y2)
    else:
        shape = Polygon([(point.x(), point.y()) for point in points])
    return shape.intersects(image)


def validate_export_shape_bounds(shape, width, height):
    if not all(math.isfinite(point.x()) and math.isfinite(point.y())
               for point in shape.pointslist):
        raise ValueError('Invalid annotation:\n'
                         f'Label: {shape.label}\nGroup ID: {shape.group_id}\n'
                         'Reason: Non-finite annotation coordinate.')
    if not shape_intersects_image(shape.pointslist, shape.shape_type, width, height):
        raise ValueError('Invalid annotation:\n'
                         f'Label: {shape.label}\nGroup ID: {shape.group_id}\n'
                         'Reason: Shape lies completely outside the image bounds.')


def parse_annotation_line(line, kind, width, height):
    parts = line.split()
    classnum = int(parts[0])
    if classnum < 0:
        raise ValueError('Class ID must be a non-negative integer')
    values = [float(token) for token in parts[1:]]
    if not all(math.isfinite(value) for value in values):
        raise ValueError('Non-finite annotation coordinate')
    if kind == 'rectangle':
        if len(values) != 4:
            raise ValueError('Rectangle requires exactly four coordinates')
        cx, cy, w, h = values
        if w <= 0 or h <= 0:
            raise ValueError('Rectangle width and height must be positive')
        points = [QPointF((cx-w/2)*width, (cy-h/2)*height),
                  QPointF((cx+w/2)*width, (cy+h/2)*height)]
    else:
        if len(values) % 2 or len(values) < (10 if kind == 'polygon' else 6):
            raise ValueError('Polygon requires at least five complete coordinate pairs'
                             if kind == 'polygon' else 'OBB requires four complete vertices')
        if kind == 'rotated_rectangle' and len(values) != 8:
            raise ValueError('OBB requires exactly four vertices')
        points = [QPointF(values[i]*width, values[i+1]*height)
                  for i in range(0, len(values), 2)]
        require_valid_polygon(points)
        if kind == 'rotated_rectangle':
            coords = np.array([(p.x(), p.y()) for p in points], dtype=np.float64)
            edges = np.roll(coords, -1, axis=0)-coords
            lengths = np.linalg.norm(edges, axis=1)
            # Text exports use six decimal places: permit only that quantization error.
            tolerance = min(4e-6*max(width, height), 1e-3*min(lengths))
            if (min(lengths) <= 0 or
                    not np.allclose(edges[:2], -edges[2:], rtol=0, atol=tolerance) or
                    abs(np.dot(edges[0], edges[1])) > tolerance*(lengths[0]+lengths[1])):
                raise ValueError('OBB vertices must form a non-degenerate rectangle in perimeter order')
    if not all(math.isfinite(p.x()) and math.isfinite(p.y()) for p in points):
        raise ValueError('Non-finite denormalized annotation coordinate')
    if not shape_intersects_image(points, kind, width, height):
        raise ValueError('Shape lies completely outside the image bounds.')
    return classnum, points


def parse_import_lines(lines, kind, width, height, checkpoint=None, with_labels=False):
    """Return valid records and line-specific rejections without changing geometry."""
    valid, skipped = [], []
    header = rectangle_table_header_index(lines) if kind == 'rectangle' else None
    for number, line in enumerate(lines, 1):
        if checkpoint is not None and number % 256 == 1:
            checkpoint()
        if not line.strip() or header == number - 1:
            continue
        try:
            if header is not None:
                category, points, label = parse_rectangle_table_line(line, width, height)
            else:
                category, points = parse_annotation_line(line, kind, width, height)
                label = None
        except (ValueError, IndexError, OverflowError) as error:
            skipped.append((number, str(error)))
        else:
            valid.append((number, category, points, label) if with_labels
                         else (number, category, points))
    return valid, skipped


def require_annotation_text(lines):
    """Reject obvious structured documents supplied through the text-file picker."""
    first = next((line.lstrip() for line in lines if line.strip()), '')
    if first.startswith(('{', '[', '<')):
        raise ValueError('Unsupported annotation file format.')


def import_warning(skipped, imported_count, limit=20):
    """One English warning for an import, with bounded detail."""
    count = len(skipped)
    if not count:
        return ''
    if imported_count:
        header = (f'The annotation file was imported, but {count} invalid '
                  f'{"shape was" if count == 1 else "shapes were"} skipped.')
    else:
        header = (f'No valid annotations were imported.\n'
                  f'All {count} {"shape was" if count == 1 else "shapes were"} invalid '
                  f'and {"was" if count == 1 else "were"} skipped.')
    detail = '\n'.join(f'{number} — {reason}' for number, reason in skipped[:limit])
    remainder = (f'\n... and {count - limit} more invalid shapes.'
                 if count > limit else '')
    footer = ('\n\nAll other valid annotations were imported successfully.'
              if imported_count else '')
    return (f'{header}\n\nSkipped {"line" if count == 1 else "lines"}:\n'
            f'{detail}{remainder}{footer}')


def validate_annotation_lines(lines, kind, width, height, path, checkpoint=None):
    """Reject a malformed file before creating or committing any Shapes."""
    errors = []
    for number, line in enumerate(lines, 1):
        if checkpoint is not None and number % 256 == 1:
            checkpoint()
        if not line.strip():
            continue
        try:
            parse_annotation_line(line, kind, width, height)
        except (ValueError, IndexError, OverflowError) as error:
            errors.append(f'{path}: line {number}: {error}')
    if errors:
        raise ValueError('\n'.join(errors))


def validate_polygon_export(content, width, height, path, shapes=None):
    """Apply the importer's exact contract to the bytes about to be saved."""
    if shapes is not None:
        for shape in shapes:
            validate_export_shape_bounds(shape, width, height)
    validate_annotation_lines(content.splitlines(), 'polygon', width, height, path)


def validate_rectangle_export(shapes, content, kind, width, height, path):
    """Check Canvas geometry and then the exact serialized importer contract."""
    minimum = minimum_rectangle_size(width, height)
    for shape in shapes:
        side_a, side_b = rectangle_side_lengths(shape.pointslist, kind)
        # Rotated vertices acquire sub-pixel floating-point error when the
        # perpendicular edge is constructed or a resize transform is applied.
        tolerance = 1e-9 * max(1.0, minimum) if kind == 'rotated_rectangle' else 0.0
        if not all(math.isfinite(value) and value >= minimum - tolerance
                   for value in (side_a, side_b)):
            raise ValueError(f'{kind} {shape.label} / {shape.group_id}: '
                             f'both sides must be at least {minimum:g} pixels.')
        validate_export_shape_bounds(shape, width, height)
    validate_annotation_lines(content.splitlines(), kind, width, height, path)
