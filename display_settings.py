"""Application-wide visual settings. No measurement data or QSettings reads in paint."""
from dataclasses import dataclass, asdict
import math
from PyQt5 import QtCore


@dataclass(frozen=True)
class Appearance:
    auto_scale: bool = True
    point_diameter: float = 8.0
    point_outline_width: float = 1.5
    point_style: str = 'circle'
    line_width: float = 1.5
    line_style: str = 'solid'


LINE_STYLES = {'solid': QtCore.Qt.SolidLine, 'dashed': QtCore.Qt.DashLine,
               'dotted': QtCore.Qt.DotLine, 'dash-dot': QtCore.Qt.DashDotLine}
current = Appearance()
revision = 0


def normalize(values):
    defaults = asdict(Appearance())
    result = dict(defaults)
    auto = values.get('auto_scale', True)
    if isinstance(auto, bool):
        result['auto_scale'] = auto
    elif str(auto).lower() in ('true', 'false', '1', '0'):
        result['auto_scale'] = str(auto).lower() in ('true', '1')
    for key, low, high in [('point_diameter', 2, 40), ('point_outline_width', .5, 10), ('line_width', .5, 10)]:
        try:
            value = float(values.get(key, defaults[key]))
            if math.isfinite(value) and low <= value <= high:
                result[key] = value
        except (TypeError, ValueError, OverflowError):
            pass
    for key, allowed in [('point_style', ('circle', 'square', 'cross')), ('line_style', LINE_STYLES)]:
        value = values.get(key, defaults[key])
        if isinstance(value, str) and value in allowed:
            result[key] = value
    return Appearance(**result)


def set_current(value):
    global current, revision
    value = value if isinstance(value, Appearance) else normalize(value)
    if value != current:
        current = value
        revision += 1


def load(settings):
    return normalize({key: settings.value('display/' + key, value) for key, value in asdict(Appearance()).items()})


def save(settings, value):
    for key, item in asdict(value).items():
        settings.setValue('display/' + key, item)


def transform_scale(transform):
    # The application uses uniform zoom; hypot also accommodates view rotation.
    return max(math.hypot(transform.m11(), transform.m12()), 1e-6)


def point_radius(scale, base_size=4):
    if current.auto_scale:
        return int(max(base_size * 1.5 / scale, 8))
    return current.point_diameter / (2 * scale)


def point_hit_radius(scale, base_size=4):
    # At least a 12 px click target, bounded independently of a thick outline.
    return max(6 / scale, min(point_radius(scale, base_size), 20 / scale))
