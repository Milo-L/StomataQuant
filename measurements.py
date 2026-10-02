"""Shared measurement freshness rules; coordinates remain in image pixels."""
from functools import wraps
import math
from numbers import Real


def finite_numeric(value):
    """Accept Python and NumPy real scalars, excluding flags and non-finite data."""
    return isinstance(value, Real) and not isinstance(value, bool) and math.isfinite(value)


def positive_number(value):
    value = float(value)
    if not math.isfinite(value) or value <= 0:
        raise ValueError('Scale distances must be finite positive numbers.')
    return value


def validated_scale(scale_info):
    if scale_info is None:
        return None
    info = dict(scale_info)
    info['scale'] = positive_number(info.get('scale', 1.0))
    if not math.isfinite(info['scale'] * info['scale']):
        raise ValueError('Scale is too large.')
    info['unit'] = info.get('unit', 'pixel')
    return info


def resolve_scale(main_window, view):
    if getattr(view, '_scale_override', False):
        return validated_scale(getattr(view, 'scale_info', None))
    return validated_scale(getattr(main_window, 'global_scale_info', None)
                           or getattr(view, 'scale_info', None))


def summary_area(size, scale_info):
    """Density uses mm² for physical scales, pixel² for uncalibrated images."""
    info = validated_scale(scale_info)
    factors = {'nm': 1e-6, 'μm': 1e-3, 'µm': 1e-3, 'um': 1e-3,
               'mm': 1., 'cm': 10., 'm': 1000., 'km': 1e6}
    if info and info['unit'] in factors:
        scale = info['scale'] * factors[info['unit']]
        return (size.width() * scale) * (size.height() * scale), 'mm²'
    if info and info['unit'] not in ('pixel', 'pixels'):
        raise ValueError('Unknown physical scale unit: ' + str(info['unit']))
    return size.width() * size.height(), 'pixel²'


def apply_scale(main_window, view, scale_info, is_global, refresh=True):
    info = validated_scale(scale_info)
    targets = [main_window.tabWidget.widget(i).property('graphics_view')
               for i in range(main_window.tabWidget.count())]
    before = [resolve_scale(main_window, target) for target in targets]
    if is_global:
        main_window.global_scale_info = info
        for target in targets:
            if target:
                target._scale_override = False
    else:
        if view is not None:
            view.scale_info = info
            view._scale_override = True
    affected = []
    for index, target in enumerate(targets):
        if target and target.canvas and before[index] != resolve_scale(main_window, target):
            affected.append(main_window.tabWidget.widget(index))
            if hasattr(target.canvas, '_measurement_scale_version'):
                target.canvas._measurement_scale_version += 1
                target.canvas._measurement_dirty.update(target.canvas._shape_by_id)
            for shape in target.canvas.shapes:
                shape._measurement_key = None
    controller = getattr(main_window, 'measurement_controller', None)
    update_status = getattr(main_window, 'update_scale_status', None)
    if update_status is not None:
        update_status()
    if refresh and controller is not None:
        controller.refresh_tabs(affected)


def measurement_key(shape, scale_info):
    scale_info = scale_info or {}
    return (shape.shape_type, shape.label, shape.group_id,
            tuple((p.x(), p.y()) for p in shape.pointslist),
            scale_info.get('scale', 1.0), scale_info.get('unit', 'pixel'))


def measured(method):
    @wraps(method)
    def wrapped(self, scale_info=None):
        scale_info = validated_scale(scale_info)
        self._measurement_scale = dict(scale_info) if scale_info else None
        self._measurement_key = None
        self.feature_results = {}
        if self.shape_type == 'polygon':
            from geometry import require_valid_polygon
            require_valid_polygon(self.pointslist)
        method(self, scale_info)
        if not self.feature_results:
            raise ValueError(f'Cannot measure {self.shape_type} {self.label} / {self.group_id}.')
        self._measurement_key = measurement_key(self, scale_info)
    return wrapped


def ensure_features(shape, scale_info, force=False):
    """Never trust an unstamped cache (including old copied/undo states)."""
    key = measurement_key(shape, scale_info)
    if force or not shape.feature_results or getattr(shape, '_measurement_key', None) != key:
        method = getattr(shape, 'feature_extraction_' + shape.shape_type)
        method(scale_info)
    return shape.feature_results


def refresh_shapes(shapes, scale_info, force=False):
    errors = []
    for shape in shapes:
        if shape.visible:
            try:
                ensure_features(shape, scale_info, force)
            except ValueError as error:
                shape.feature_results = {}
                errors.append(f'{shape.label} / {shape.group_id}: {error}')
    return errors
