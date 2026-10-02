"""Bounded, shared annotation snapshots. Never stores live Qt objects or changes formats."""
import copy
import itertools
import sys
import weakref
from numpy import float32, float64, int32, int64

_identities = itertools.count(1)


def shape_identity(shape):
    """Shared lifetime-independent identity (also preserved by Undo/Redo)."""
    if not hasattr(shape, '_history_id'):
        shape._history_id = next(_identities)
    return shape._history_id
_stores = weakref.WeakSet()
MAX_STEPS = 30
PER_IMAGE_BYTES = 64 * 1024 * 1024
TOTAL_BYTES = 192 * 1024 * 1024
_SCALAR_TYPES = frozenset((type(None), bool, int, float, complex, str, bytes,
                           float32, float64, int32, int64))


def copy_payload(value):
    """Flat measurement records contain immutable scalars; copy their container.

    Nested/custom audit payloads retain the full deep-copy path. The fast path
    counts every entry conservatively, including repeated scalar references.
    """
    if value is None:
        return None, sys.getsizeof(None)
    if type(value) is dict and all(type(k) is str and type(v) in _SCALAR_TYPES
                                   for k, v in value.items()):
        result = value.copy()
        size = sys.getsizeof(result) + sum(sys.getsizeof(k) + sys.getsizeof(v)
                                          for k, v in result.items())
        return result, size
    result = copy.deepcopy(value)
    return result, deep_size(result)


def deep_size(value, seen=None):
    seen = set() if seen is None else seen
    if id(value) in seen:
        return 0
    seen.add(id(value))
    size = sys.getsizeof(value)
    if isinstance(value, dict):
        size += sum(deep_size(k, seen) + deep_size(v, seen) for k, v in value.items())
    elif isinstance(value, (list, tuple, set)):
        size += sum(deep_size(v, seen) for v in value)
    return size


class Record(dict):
    """Private immutable-by-convention record, copied before applying to live shapes."""
    pass


class History:
    def __init__(self):
        self.undo = []
        self.redo = []
        self.cache = {}
        self.budget = PER_IMAGE_BYTES
        self.max_steps = MAX_STEPS
        _stores.add(self)

    def capture(self, shapes):
        result = []
        cache = {}
        for shape in shapes:
            shape_identity(shape)
            state = dict(_history_id=shape._history_id, label=shape.label, classnum=shape.classnum,
                         pointslist=tuple((p.x(), p.y()) for p in shape.pointslist),
                         shape_type=shape.shape_type, group_id=shape.group_id, visible=shape.visible,
                         rotated_angle=shape.rotated_angle, _show_group_id=shape._show_group_id,
                         feature_results=shape.feature_results, unit=shape.unit,
                         measurement_error=getattr(shape, 'measurement_error', None),
                         _measurement_scale=shape._measurement_scale,
                         _measurement_key=getattr(shape, '_measurement_key', None),
                         _show_points=shape._show_points, polygon_audit=getattr(shape, 'polygon_audit', None))
            previous = self.cache.get(shape._history_id)
            if previous is not None and previous == state:
                record = previous
            else:
                # Coordinates and measurement provenance are immutable tuples.
                # Copy only mutable payloads, never walk/copy every coordinate twice.
                record = Record(state)
                payload_bytes = 0
                for key in ('feature_results', '_measurement_scale', 'polygon_audit'):
                    record[key], size = copy_payload(state[key])
                    payload_bytes += size
                # Conservative retained-memory bound: 256 B/vertex covers both
                # coordinate tuple graphs (including their floats); the fixed
                # allowance covers keys, scalar metadata and Record attributes.
                # Variable strings/payloads are counted separately, not truncated.
                record.nbytes = (sys.getsizeof(record) + 4096 + 256 * len(state['pointslist'])
                                 + sum(sys.getsizeof(state[k]) for k in ('label','classnum','group_id','unit'))
                                 + payload_bytes)
            result.append(record)
            cache[shape._history_id] = record
        self.cache = cache
        return result

    @staticmethod
    def same_content(first, second):
        # Invalidating an otherwise identical cache is not an annotation edit.
        return len(first) == len(second) and all(
            a is b or all(a[key] == b[key] for key in a if key not in ('_measurement_key', 'measurement_error'))
            for a,b in zip(first,second))

    @property
    def bytes(self):
        records = {id(r): r for frame in self.undo + self.redo for r in frame}
        records.update((id(r), r) for r in self.cache.values())
        return (sum(r.nbytes if isinstance(r, Record) else deep_size(r) for r in records.values())
                + sum(sys.getsizeof(frame) for frame in self.undo + self.redo)
                + sys.getsizeof(self.cache) + sys.getsizeof(self.undo) + sys.getsizeof(self.redo))

    def trim(self):
        while len(self.undo) + len(self.redo) > self.max_steps:
            (self.undo if self.undo else self.redo).pop(0)
        while self.bytes > self.budget:
            if self.undo:
                self.undo.pop(0)
            elif self.redo:
                self.redo.pop(0)
            else:
                self.cache.clear()
                break
        stores = list(_stores)
        # Across open images, discard old history from the largest store first.
        while sum(store.bytes for store in stores) > TOTAL_BYTES:
            largest = max(stores, key=lambda store: store.bytes)
            if largest.undo:
                largest.undo.pop(0)
            elif largest.redo:
                largest.redo.pop(0)
            else:
                largest.cache.clear()

    def clear(self):
        self.undo.clear()
        self.redo.clear()
        self.cache.clear()
