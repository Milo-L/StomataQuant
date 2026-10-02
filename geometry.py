"""Geometry conventions shared by drawing, imports and measurements."""
import math
import weakref
import numpy as np
import cv2
from shapely.geometry import Polygon
from shapely.validation import explain_validity, make_valid


MIN_POLYGON_VERTICES = 5


def minimum_rectangle_size(image_width, image_height):
    """One pixel, or two steps of the six-decimal YOLO rectangle width field."""
    if image_width <= 0 or image_height <= 0:
        raise ValueError('Image dimensions must be positive.')
    return max(1.0, 2e-6 * max(image_width, image_height))


def rectangle_side_lengths(points, kind):
    if kind == 'rectangle':
        if len(points) != 2:
            raise ValueError('Rectangle requires two vertices.')
        return abs(points[1].x() - points[0].x()), abs(points[1].y() - points[0].y())
    if kind == 'rotated_rectangle':
        if len(points) != 4:
            raise ValueError('OBB requires four vertices.')
        return (math.hypot(points[1].x() - points[0].x(), points[1].y() - points[0].y()),
                math.hypot(points[2].x() - points[1].x(), points[2].y() - points[1].y()))
    raise ValueError('Unsupported rectangle kind.')


def polygon_moments(points):
    """Area centroid and eccentricity of a uniformly filled polygon (float64)."""
    polygon = Polygon([(p.x(), p.y()) for p in points])
    if not polygon.is_valid or polygon.area <= 0:
        raise ValueError('Invalid polygon: ' + explain_validity(polygon))
    center = polygon.centroid
    coords = np.asarray(polygon.exterior.coords[:-1], dtype=np.float64)
    # Integrate around the centroid to avoid subtracting large raw moments.
    coords -= (center.x, center.y)
    following = np.roll(coords, -1, axis=0)
    x, y = coords.T
    u, v = following.T
    cross = x*v-u*y
    area = math.fsum(cross)/2
    xx = math.fsum((x*x+x*u+u*u)*cross)/(12*area)
    yy = math.fsum((y*y+y*v+v*v)*cross)/(12*area)
    xy = math.fsum((2*x*y+x*v+u*y+2*u*v)*cross)/(24*area)
    small, large = np.linalg.eigvalsh([[xx, xy], [xy, yy]])
    eccentricity = math.sqrt(max(0., min(1., 1-small/large))) if large > 0 else 0.
    return polygon, (center.x, center.y), eccentricity


def require_valid_polygon(points):
    coords = [(p.x(), p.y()) for p in points]
    if len(set(coords)) < 3 or not np.isfinite(coords).all():
        raise ValueError('Polygon needs at least three distinct finite vertices.')
    polygon = Polygon(coords)
    if not polygon.is_valid or polygon.area <= 0:
        raise ValueError('Invalid polygon: ' + explain_validity(polygon))


def repair_polygon(xs, ys):
    """Conservative repair; callers reject ambiguous results before creating Shapes."""
    original = (list(xs), list(ys))
    record = {'original_x': list(xs), 'original_y': list(ys), 'status': 'unchanged',
              'area_before': None, 'area_after': None, 'relative_area_change': None}
    if len(xs) != len(ys) or len(set(zip(xs, ys))) < 3 or not np.isfinite(list(zip(xs, ys))).all():
        record.update(status='rejected', reason='Non-finite, mismatched or degenerate vertices')
        return original, record
    coords = []
    for point in zip(xs, ys):
        if not coords or point != coords[-1]:
            coords.append(point)
    poly = Polygon(coords)
    record['area_before'] = poly.area
    if poly.is_valid and poly.area > 0:
        record['area_after'] = poly.area
        record['relative_area_change'] = 0.
        if len(coords) != len(xs):
            record['status'] = 'repaired'
        return (list(p[0] for p in coords), list(p[1] for p in coords)), record
    fixed = make_valid(poly)
    record.update(reason=explain_validity(poly), area_after=fixed.area)
    change = abs(fixed.area-poly.area)/poly.area if poly.area > 0 else None
    record['relative_area_change'] = change
    # The existing TXT format cannot represent holes or multiple components.
    if (fixed.geom_type == 'Polygon' and fixed.is_valid and fixed.area > 0
            and not fixed.interiors and change is not None and change <= .01):
        x, y = fixed.exterior.xy
        record['status'] = 'repaired'
        return (list(x), list(y)), record
    record['status'] = 'rejected'
    return original, record


class ProcessedPolygons(dict):
    def __init__(self):
        super().__init__()
        self.audit = []


def rectangle_angle(points):
    """Undirected long-axis angle in Qt's CCW convention, [0, 180) degrees.

    For squares the smaller of the two axis angles is used. Vertex start and
    winding order therefore do not affect the measurement.
    """
    coords = np.asarray([(p.x(), p.y()) for p in points], dtype=float)
    edges = np.roll(coords, -1, axis=0) - coords
    lengths = np.linalg.norm(edges, axis=1)
    angles = []
    for edge, length in zip(edges, lengths):
        if np.isclose(length, max(lengths), rtol=1e-6, atol=1e-8):
            angle = (-math.degrees(math.atan2(edge[1], edge[0]))) % 180
            angles.append(0. if abs(angle-180) < 1e-5 or abs(angle) < 1e-5 else angle)
    return min(angles) if angles else 0.


def minimum_area_rectangle(points):
    require_valid_polygon(points)
    coords = np.asarray([(p.x(), p.y()) for p in points], dtype=np.float32)
    if len(coords) < 3 or not np.isfinite(coords).all() or cv2.contourArea(coords) <= 0:
        raise ValueError('MER requires a finite, non-degenerate polygon.')
    return cv2.minAreaRect(coords)


class Points(list):
    def __init__(self, values, owner):
        super().__init__(values)
        self._owner = weakref.ref(owner)

    def _changed(self):
        owner = self._owner()
        if owner is not None:
            owner.geometry_changed()

    def __setitem__(self, key, value):
        super().__setitem__(key, value); self._changed()

    def __delitem__(self, key):
        super().__delitem__(key); self._changed()

    def append(self, value):
        super().append(value); self._changed()

    def extend(self, values):
        super().extend(values); self._changed()

    def insert(self, index, value):
        super().insert(index, value); self._changed()

    def pop(self, index=-1):
        value = super().pop(index); self._changed(); return value

    def remove(self, value):
        super().remove(value); self._changed()

    def clear(self):
        super().clear(); self._changed()

    def reverse(self):
        super().reverse(); self._changed()

    def sort(self, *args, **kwargs):
        super().sort(*args, **kwargs); self._changed()

    def __iadd__(self, values):
        self.extend(values); return self

    def __imul__(self, count):
        super().__imul__(count); self._changed(); return self
