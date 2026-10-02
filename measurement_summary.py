"""Reversible statistics and sorted medians; no scan after a single edit."""
import bisect
import math
from fractions import Fraction
from collections import Counter
from PyQt5 import QtCore
from measurement_rows import KINDS, write_cells
from measurements import finite_numeric


class Moments:
    """Exact binary sums avoid cancellation/drift when outliers are removed."""
    def __init__(self):
        self.values = []
        self.total = self.squares = 0

    @staticmethod
    def integer(value):
        numerator, denominator = float(value).as_integer_ratio()
        return numerator << (1074 - (denominator.bit_length() - 1))

    def add(self, value):
        value = float(value)
        if not math.isfinite(value):
            raise ValueError('Non-finite measurement cannot enter summary.')
        integer = self.integer(value)
        bisect.insort(self.values, value)
        self.total += integer
        self.squares += integer * integer

    def remove(self, value):
        value = float(value)
        index = bisect.bisect_left(self.values, value)
        if index == len(self.values) or self.values[index] != value:
            raise ValueError('Missing summary contribution.')
        self.values.pop(index)
        integer = self.integer(value)
        self.total -= integer
        self.squares -= integer * integer

    def result(self):
        n = len(self.values)
        if not n:
            return None
        mean = float(Fraction(self.total, n << 1074))
        try:
            variance = float(Fraction(self.squares * n - self.total * self.total, (n*n) << 2148))
        except OverflowError:
            # Match NumPy's overflowing float64 population variance, without
            # allowing an exception to escape a Qt update slot.
            variance = math.inf
        middle = n // 2
        median = self.values[middle] if n % 2 else (self.values[middle-1] + self.values[middle]) / 2
        return n, mean, math.sqrt(variance), median, self.values[0], self.values[-1]


class IncrementalSummary:
    def __init__(self):
        self.records, self.bins = {}, {}
        self.counts = Counter()

    def update(self, uid, record=None):
        feature_keys, count_keys = set(), set()
        new_features = None
        if record is not None:
            kind, label, results = record
            new_features = {name: float(value) for name, value in results.items()
                            if name not in ('Label', 'Group ID', 'Center Point', 'Start Point', 'End Point')
                            and finite_numeric(value)}
            previous = self.records.get(uid)
            if previous is not None and previous[0] == kind and previous[2] == new_features:
                self.records[uid] = kind, label, new_features
                if previous[1] != label:
                    old_key, new_key = (previous[1], kind), (label, kind)
                    self.counts[old_key] -= 1
                    if not self.counts[old_key]:
                        del self.counts[old_key]
                    self.counts[new_key] += 1
                    count_keys.update((old_key, new_key))
                return feature_keys, count_keys
        old = self.records.pop(uid, None)
        if old is not None:
            kind, label, features = old
            self.counts[label, kind] -= 1
            count_keys.add((label, kind))
            if not self.counts[label, kind]:
                del self.counts[label, kind]
            for name, value in features.items():
                key = kind, name
                self.bins[key].remove(value)
                feature_keys.add(key)
                if not self.bins[key].values:
                    del self.bins[key]
        if record is not None:
            kind, label, results = record
            features = new_features
            self.records[uid] = kind, label, features
            self.counts[label, kind] += 1
            count_keys.add((label, kind))
            for name, value in features.items():
                key = kind, name
                self.bins.setdefault(key, Moments()).add(value)
                feature_keys.add(key)
        return feature_keys, count_keys


class SummaryRows:
    def __init__(self, dock):
        self.dock = dock
        self.feature_rows, self.count_rows = {}, {}

    @staticmethod
    def cells(table, index, key, count=False):
        # Qt invalidates a persistent index on deletion; no destroyed item is retained.
        if index is not None and index.isValid():
            cells = [table.item(index.row(), column) for column in range(table.columnCount())]
            if all(cell is not None for cell in cells):
                return cells
        # Compatibility refreshes rebuild items independently of this projection.
        # Rebind their logical keys instead of appending duplicate aggregate rows.
        for row in range(table.rowCount()):
            first = table.item(row, 0)
            if first is None:
                continue
            matches = (first.text() == str(key[0]) and table.item(row, 1) is not None
                       and table.item(row, 1).text() == key[1]) if count else first.text() == key[1]
            if matches:
                cells = [table.item(row, column) for column in range(table.columnCount())]
                if all(cell is not None for cell in cells):
                    return cells
        return None

    @staticmethod
    def index(table, cells):
        return QtCore.QPersistentModelIndex(table.indexFromItem(cells[0]))

    def clear(self):
        self.feature_rows.clear()
        self.count_rows.clear()
        for table in [self.dock.summary_table] + [getattr(self.dock, k + '_table') for k in KINDS]:
            blocker = QtCore.QSignalBlocker(table)
            table.setRowCount(0)
            del blocker

    def write(self, summary, feature_keys, count_keys, size, scale):
        scale = scale or {}
        # Preserve the original multiplication order and display units.
        from measurements import summary_area
        area, unit = summary_area(size, scale)
        self.dock.summary_table.setProperty('density_unit', 'count/' + unit)
        self.dock.summary_table.setProperty('image_area_unit', unit)
        for key in feature_keys:
            table = getattr(self.dock, key[0] + '_table')
            cells = self.cells(table, self.feature_rows.get(key), key)
            bin = summary.bins.get(key)
            blocker = QtCore.QSignalBlocker(table)
            if bin is None:
                if cells:
                    table.removeRow(cells[0].row())
                self.feature_rows.pop(key, None)
            else:
                result = bin.result()
                values = [key[1], str(result[0])] + [f'{v:.4f}' for v in result[1:]]
                cells = write_cells(table, cells, values, raw_values=[key[1], *result])
                self.feature_rows[key] = self.index(table, cells)
            del blocker
        table = self.dock.summary_table
        blocker = QtCore.QSignalBlocker(table)
        for key in count_keys:
            cells = self.cells(table, self.count_rows.get(key), key, count=True)
            count = summary.counts.get(key, 0)
            if not count:
                if cells:
                    table.removeRow(cells[0].row())
                self.count_rows.pop(key, None)
            else:
                density = count / area if area else 0.
                values = [str(key[0]), key[1], str(count), f'{density:.3e} count/{unit}', f'{area:.4f} {unit}']
                cells = write_cells(table, cells, values,
                                    raw_values=[str(key[0]), key[1], count, density, area])
                self.count_rows[key] = self.index(table, cells)
        del blocker
