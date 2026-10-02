"""Conservative visual-bounds grid; exact hit/paint rules remain in Canvas/Shape."""
import math
import weakref
from PyQt5 import QtCore, QtGui
import display_settings as display


class ShapeList(list):
    def __init__(self, values, index, owner=None):
        super().__init__(values)
        self.index = index
        self.owner = weakref.ref(owner) if owner is not None else lambda: None
        index.members_dirty = True

    def changed(self, check_removed=False):
        self.index.members_dirty = True
        # A small scene bypasses query(), so it must not retain removed members.
        if not self.index.members or not check_removed:
            return
        members = {id(shape) for shape in self}
        for ident, shape in list(self.index.members.items()):
            if ident not in members:
                shape._spatial_indexes.discard(self.index)
                self.index.drop(ident)
                del self.index.members[ident]
                self.index.order.pop(ident, None)
        self.index.pending.intersection_update(members)
    def notify(self, added=(), removed=()):
        owner = self.owner()
        if owner is not None:
            owner.measurement_members_changed(added, removed)
    def validate(self, added, removed=()):
        owner = self.owner()
        if owner is not None:
            owner.measurement_validate_members(added, removed)
    def append(self, x): self.validate((x,)); super().append(x); self.changed(); self.notify((x,))
    def extend(self, x):
        x=list(x);self.validate(x);super().extend(x);self.changed();self.notify(x)
    def insert(self, i, x): self.validate((x,)); super().insert(i, x); self.changed(); self.notify((x,))
    def pop(self, i=-1):
        x=super().pop(i);self.changed(True);self.notify(removed=(x,));return x
    def clear(self):
        old=list(self);super().clear();self.changed(True);self.notify(removed=old)
    def remove(self, x):
        # Shapes can compare equal geometrically; membership is object identity.
        position = next((i for i, shape in enumerate(self) if shape is x), None)
        if position is None:
            raise ValueError('Shape is not in this Canvas.')
        super().pop(position);self.changed(True);self.notify(removed=(x,))
    def __setitem__(self, i, x):
        old=self[i];x=list(x) if isinstance(i,slice) else x
        self.validate(x if isinstance(i,slice) else (x,), old if isinstance(i,slice) else (old,))
        super().__setitem__(i,x);self.changed(True)
        self.notify(x if isinstance(i,slice) else (x,), old if isinstance(i,slice) else (old,))
    def __delitem__(self, i):
        old=self[i];super().__delitem__(i);self.changed(True)
        self.notify(removed=old if isinstance(i,slice) else (old,))
    def reverse(self): super().reverse();self.changed()
    def sort(self, *a, **kw): super().sort(*a,**kw);self.changed()
    def __iadd__(self, x): self.extend(x);return self
    def __imul__(self, n):
        old=list(self);self.validate(old*n,old);super().__imul__(n);self.changed(True);self.notify(self,old);return self


class Grid:
    def __init__(self):
        self.members_dirty = True
        self.members = {}
        self.order = {}
        self.cells = {}
        self.keys = {}
        self.overflow = set()
        self.pending = set()
        self.context = None
        self.font = QtGui.QFont()
        self.last_candidates = 0

    def changed(self, shape):
        self.pending.add(id(shape))

    @staticmethod
    def cell_keys(rect):
        if not all(math.isfinite(v) for v in (rect.left(),rect.right(),rect.top(),rect.bottom())):
            return None
        x0,x1=math.floor(rect.left()/128),math.floor(rect.right()/128)
        y0,y1=math.floor(rect.top()/128),math.floor(rect.bottom()/128)
        if (x1-x0+1)*(y1-y0+1)>4096:
            return None
        return [(x,y) for x in range(x0,x1+1) for y in range(y0,y1+1)]

    def drop(self, ident):
        for key in self.keys.pop(ident, ()):
            bucket=self.cells[key];bucket.discard(ident)
            if not bucket:del self.cells[key]
        self.overflow.discard(ident)

    def put(self, shape, scale):
        ident=id(shape)
        self.drop(ident)
        rect=shape.visual_bounds(self.font,None if display.current.auto_scale else scale)
        keys=self.cell_keys(rect)
        if keys is None or len(keys)>256:
            self.overflow.add(ident)
        else:
            self.keys[ident]=keys
            for key in keys:self.cells.setdefault(key,set()).add(ident)

    def query(self, shapes, rect, scale, font=None):
        if font is not None:self.font=QtGui.QFont(font)
        context=(scale,display.revision,self.font.toString())
        if self.members_dirty or context!=self.context:
            members={id(s):s for s in shapes}
            added = members.keys() - self.members.keys()
            for ident,shape in self.members.items():
                if ident not in members:
                    shape._spatial_indexes.discard(self)
                    self.drop(ident)
            self.members=members;self.order={id(s):i for i,s in enumerate(shapes)}
            if context!=self.context:
                self.cells.clear();self.keys.clear();self.overflow.clear()
                affected = members.keys()
            else:
                # Membership/order changes do not invalidate unchanged bounds.
                affected = (added | self.pending) & members.keys()
            for ident in affected:
                shape = members[ident]
                if not hasattr(shape,'_spatial_indexes'):shape._spatial_indexes=weakref.WeakSet()
                shape._spatial_indexes.add(self)
                self.put(shape,scale)
            self.context=context;self.members_dirty=False;self.pending.clear()
        elif self.pending:
            for ident in self.pending:
                if ident in self.members:self.put(self.members[ident],scale)
            self.pending.clear()
        keys=self.cell_keys(rect)
        if keys is None:
            result=list(shapes)
        else:
            candidates=set(self.overflow)
            for key in keys:candidates.update(self.cells.get(key,()))
            result=[self.members[i] for i in sorted(candidates,key=self.order.__getitem__)]
        self.last_candidates=len(result)
        return result
