"""Selected-only annotation export; validate the whole selection before writing."""
import math
from annotation_io import parse_annotation_line
from point_annotations import class_id, image_dimensions


def serialize_selected(canvas, shapes):
    shapes = list(shapes)
    kinds = {shape.shape_type for shape in shapes}
    if len(kinds) != 1:
        raise ValueError('Select shapes of exactly one type. Mixed shape types cannot be exported.')
    kind = next(iter(kinds))
    if kind not in ('point', 'polygon', 'rectangle', 'rotated_rectangle'):
        raise ValueError('Annotation export supports Point, Polygon, Rectangle and Rotated Rectangle.')
    width, height = image_dimensions(canvas)
    lines = []
    for shape in shapes:
        if not any(item is shape for item in canvas.shapes):
            raise ValueError('Selected shapes no longer belong to the current image.')
        category = class_id(shape.classnum)
        points = [(point.x(), point.y()) for point in shape.pointslist]
        if not all(math.isfinite(value) for point in points for value in point):
            raise ValueError('Selected shape has non-finite coordinates.')
        if kind == 'point':
            if len(points) != 1 or not 0 <= points[0][0] <= width or not 0 <= points[0][1] <= height:
                raise ValueError('A Point requires one coordinate inside the image.')
            values = [points[0][0] / width, points[0][1] / height]
        elif kind == 'rectangle':
            if len(points) != 2:
                raise ValueError('A Rectangle requires two diagonal vertices.')
            (x1, y1), (x2, y2) = points
            values = [(x1 + x2) / (2 * width), (y1 + y2) / (2 * height),
                      abs(x2 - x1) / width, abs(y2 - y1) / height]
        else:
            values = [value for x, y in points for value in (x / width, y / height)]
        line = str(category) + ' ' + ' '.join(format(value, '.17g') for value in values)
        if kind != 'point':
            try:
                parse_annotation_line(line, kind, width, height)
            except ValueError as error:
                raise ValueError(f'Invalid annotation:\nLabel: {shape.label}\n'
                                 f'Group ID: {shape.group_id}\nReason: {error}') from error
        lines.append(line + '\n')
    return kind, ''.join(lines)
