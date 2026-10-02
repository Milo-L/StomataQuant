# shape.py
from PyQt5 import QtCore, QtGui
from PyQt5.QtCore import QPointF, QRectF
from PyQt5.QtGui import QColor
from PyQt5.QtWidgets import QGraphicsItem
import numpy as np
import cv2
import copy
import weakref
import itertools
from shape_history import shape_identity
import display_settings as display
from measurements import measured
from geometry import polygon_moments, minimum_area_rectangle, rectangle_angle, Points, MIN_POLYGON_VERTICES
from shapely.geometry import Polygon
from scipy.ndimage import distance_transform_edt

_measurement_revisions = itertools.count(1)

class Shape(QGraphicsItem):
    _spatial_fields = frozenset(('shape_type','scale_factor','_show_group_id','group_id',
                                'base_point_size','base_pen_width'))

    def __setattr__(self, name, value):
        previous = getattr(self, name, None) if name in ('label', 'classnum', 'group_id', 'shape_type', 'visible') else None
        super().__setattr__(name,value)
        if name in self._spatial_fields:
            self._notify_spatial()
        if name in ('label', 'classnum', 'group_id', 'shape_type', 'visible') and previous != value:
            self._notify_measurement(metadata=name != 'shape_type')

    def _notify_measurement(self, metadata=False):
        # New objects restored under an old history ID also get a new revision.
        self._measurement_revision = next(_measurement_revisions)
        key = getattr(self, '_measurement_key', None)
        if metadata and key is not None and getattr(self, 'feature_results', None):
            # These fields do not affect the scientific geometry calculations.
            # Reuse only a stamped cache, preserving its coordinates/scale.
            features = self.feature_results.copy()
            features['Label'] = self.label
            features['Group ID'] = self.group_id
            self.feature_results = features
            self._measurement_key = (key[0], self.label, self.group_id, *key[3:])
        else:
            self._measurement_key = None
        for canvas in getattr(self, '_measurement_owners', ()):
            canvas.measurement_changed(self)

    def _notify_spatial(self):
        for index in getattr(self,'_spatial_indexes', ()):
            index.changed(self)

    color_map = {
    0: QtGui.QColor(0, 0, 255),  # 蓝色
    1: QtGui.QColor(255, 0, 0),  # 红色
    2: QtGui.QColor(255, 255, 0),  # 黄色
    3: QtGui.QColor(0, 255, 0),  # 绿色
    4: QtGui.QColor(0, 255, 255),  # 青色
    5: QtGui.QColor(255, 0, 255),  # 洋红色
}

    def __init__(self, label=None, classnum=None, pointslist=None, shape_type='polygon', group_id=None,parent=None, scale_factor=1):
        super(Shape, self).__init__(parent)
        self.setCacheMode(QGraphicsItem.DeviceCoordinateCache)
        self.label = label
        self.classnum = int(classnum) if classnum is not None else None
        self.pointslist = pointslist if pointslist else []
        self.shape_type = shape_type
        self.group_id = group_id
        self.visible = True  # 用于标记是否可见
        self.hovered_point_index = None  # 用于标记悬停的点
        self.base_pen_width = 1.5 # 基础笔宽
        self.base_point_size = 4 # 基础点大小
                # 初始化私有属性
        self._selected = False  # 用于标记是否被选中
        self.rotated_angle = 0
        self.sync_rotated_angle()
        self.feature_results = {}
        self.measurement_error = None
        self.unit = 'pixel'
        self._measurement_scale = None
        self._show_group_id = False
        self._show_points = False
        self._dirty = False  # 标记是否需要更新
        self.scale_factor = scale_factor  # 新增属性，用于存储缩放因子

        # QGraphicsItem 属性设置
        self.setFlag(QGraphicsItem.ItemIsSelectable, True)
        self.setFlag(QGraphicsItem.ItemIsMovable, True)
        self.setAcceptHoverEvents(True)
        shape_identity(self)
        self._measurement_owners = weakref.WeakSet()
        
    def set_scale_factor(self, factor):
        """设置缩放因子"""
        if self.scale_factor == factor:
            return
        self.prepareGeometryChange()
        self.scale_factor = factor
        self._dirty = True
        QGraphicsItem.update(self)

    def appearance_changed(self):
        self._notify_spatial()
        """Call after prepareGeometryChange and the shared appearance change."""
        self._geometry_cache.pop('visual', None)
        self._geometry_cache.pop('hit_path', None)
        self._dirty = True
        QGraphicsItem.update(self)

    def moveBy(self, dx, dy):
        if dx == 0 and dy == 0:
            return
        self.prepareGeometryChange()  # 通知几何形状变化
        self.pointslist = [QtCore.QPointF(p.x() + dx, p.y() + dy) for p in self.pointslist]
        self.update_shape() # 只更新这个形状

    def copy(self):
        """创建并返回形状的新副本，不依赖于深拷贝"""
        new_shape = Shape(
            label=self.label,
            classnum=self.classnum,
            pointslist=[QPointF(p.x(), p.y()) for p in self.pointslist if p is not None],
            shape_type=self.shape_type,
            group_id=self.group_id
        )
        # 复制其他必要属性
        new_shape.visible = self.visible
        new_shape._selected = self._selected
        new_shape.rotated_angle = self.rotated_angle
        new_shape._show_group_id = self._show_group_id
        new_shape.feature_results = copy.deepcopy(self.feature_results)
        new_shape.measurement_error = self.measurement_error
        new_shape.unit = self.unit
        new_shape._measurement_scale = copy.deepcopy(self._measurement_scale)
        new_shape._show_points = self._show_points
        new_shape.scale_factor = self.scale_factor
        new_shape.polygon_audit = copy.deepcopy(getattr(self, 'polygon_audit', None))


        return new_shape

    @property
    def pointslist(self):
        return self._pointslist

    @pointslist.setter
    def pointslist(self, values):
        self._pointslist = Points(values, self)
        self.geometry_changed()

    def geometry_changed(self):
        self._notify_measurement()
        self._notify_spatial()
        self._geometry_cache = {}
        self.sync_rotated_angle()
        self._measurement_key = None
        self._dirty = True

    def cached_polygon(self):
        if 'polygon' not in self._geometry_cache:
            self._geometry_cache['polygon'] = QtGui.QPolygonF(self.pointslist)
        return self._geometry_cache['polygon']

    def cached_vertices(self):
        if 'vertices' not in self._geometry_cache:
            points = np.array([(p.x(), p.y()) for p in self.pointslist], dtype=float)
            self._geometry_cache['vertices'] = (points[:, 0].copy(), points[:, 1].copy())
        return self._geometry_cache['vertices']

    def get_bounding_rect(self):
        if 'bounds' not in self._geometry_cache:
            self._geometry_cache['bounds'] = self._calculate_bounds()
        return QRectF(self._geometry_cache['bounds'])

    def visual_bounds(self, font=None, scale=None):
        """Conservative bounds including constant-screen-size handles and labels."""
        scale = max(self.scale_factor if scale is None else scale, 0.0001)
        key = (scale, self.shape_type, self.base_point_size, self.base_pen_width,
               display.revision,
               self._show_group_id, self.group_id,
               font.toString() if font is not None and self._show_group_id else None)
        cached = self._geometry_cache.get('visual')
        if cached is not None and cached[0] == key:
            return QRectF(cached[1])
        padding = max(12 / scale, 4)
        if not display.current.auto_scale:
            padding = max(12., display.current.line_width / 2 + 2,
                          display.current.point_diameter / 2 + 2) / scale
        elif self.shape_type == 'point':
            padding = max(padding, display.point_radius(scale, self.base_point_size)
                          + max(self.base_pen_width / scale, 1) * 1.5 + 2 / scale)
        rect = self.get_bounding_rect().adjusted(-padding, -padding, padding, padding)
        if self.shape_type == 'rotated_rectangle' and len(self.pointslist) == 4:
            handle = self.get_rotation_handle_position()
            rect = rect.united(QRectF(handle.x()-padding, handle.y()-padding, 2*padding, 2*padding))
        if self._show_group_id and self.group_id is not None:
            font = QtGui.QFont(font) if font is not None else QtGui.QFont()
            font.setPointSize(int(max(min(14 / scale, 64), 8)))
            text_rect = QtGui.QFontMetricsF(font).boundingRect(str(self.group_id))
            text_rect.translate(self.get_center())
            rect = rect.united(text_rect.adjusted(-2, -2, 2, 2))
        self._geometry_cache['visual'] = (key, rect)
        return QRectF(rect)

    def _calculate_bounds(self):
        if not self.pointslist:
            return QRectF()
        min_x = min(point.x() for point in self.pointslist)
        min_y = min(point.y() for point in self.pointslist)
        max_x = max(point.x() for point in self.pointslist)
        max_y = max(point.y() for point in self.pointslist)

        return QRectF(min_x, min_y, max_x - min_x, max_y - min_y)

######################################################################
# 针对多边形的点的编辑，去除或增加点，在canvas.py种被调用
# For the editing of points within polygons, such as removing or adding points,
# this methods is called in canvas.py.
######################################################################
    def add_point(self, index, point):
        """在指定索引处添加新点"""
        self.pointslist.insert(index, point)

    def remove_point(self, index):
        """删除指定索引的点"""
        try:
            if self.shape_type == 'polygon' and len(self.pointslist) > MIN_POLYGON_VERTICES:
                del self.pointslist[index]
                return True
            else:
                return False
        except Exception as e:
            print(f"删除点时出错: {e}")
            return False

######################################################################
# Getter方法：使用 @ property 装饰器定义的;selected方法，用于获取属性值。
# Getter method: Defined using the @property decorator;The selected method is used to obtain the attribute value.
# Setter方法：使用 @ selected.setter装饰器定义的;selected方法，用于设置属性值。
# Setter method: Defined using the @selected.setter decorator;The selected method is used to set the attribute value.
######################################################################
    @property
    def selected(self):
        return self._selected

    @selected.setter
    def selected(self, value):
        if self._selected != value:
            self._selected = value
            self.update()

###########################################################################
# @classmethod 装饰器在 Python 中用于定义一个类方法。
# The @classmethod decorator is used in Python to define a class method.
# 类方法的第一个参数是 cls，它指代类本身，而不是类的实例。
# The first parameter of a class method is cls, which refers to the class itself rather than an instance of the class.
# 这意味着类方法可以直接通过类来调用，而不需要创建类的实
# This means that class methods can be called directly through the class without the need to create an instance of the class.
###########################################################################
    @classmethod
    def get_color_by_classnum(cls, classnum):
        """安全地根据类别编号获取颜色"""
        # 添加完整的类型和值检查
        if classnum is None:
            return QtGui.QColor(0, 0, 0)  # 使用RGB值而非名称
        # 尝试转换为整数
        try:
            class_index = int(classnum)
        except (TypeError, ValueError):
            return QtGui.QColor(0, 0, 0)  # 使用RGB值而非名称
            
        # 使用类变量中的颜色映射
        return cls.color_map.get(class_index, QtGui.QColor(0, 0, 0))
        
    @classmethod
    def set_color_map(cls, new_color_map):
        """设置全局颜色映射"""
        cls.color_map = new_color_map

######################################################################
# 关于group_id的显示和隐藏
# Show and hide group_id
######################################################################
    def show_group_id(self):
        self._show_group_id = True

    def hide_group_id(self):
        self._show_group_id = False

######################################################################
# 将所有形状显示为piont
# Show all shapes as piont
######################################################################
    # def get_universe_central_point(self):
    #     """
    #     计算形状的宇宙中心点，确保中心点位于形状内部。
    #     """
    #     # 获取初始中心点
    #     center = self.get_center()

    #     # 对矩形进行特殊处理
    #     if self.shape_type == "rectangle" and len(self.pointslist) == 2:
    #         # 直接使用 QRectF 判断中心点是否在矩形内
    #         rect = QtCore.QRectF(self.pointslist[0], self.pointslist[1])
    #         if not rect.contains(center):
    #             # 如果中心点不在矩形内(这种情况理论上不应该发生，但以防万一)
    #             # 计算矩形的真实中心
    #             center = QPointF(rect.center())
    #     else:
    #         # 对多边形和旋转矩形使用原有的路径检查逻辑
    #         path = QtGui.QPainterPath()
    #         if len(self.pointslist) > 0:
    #             path.moveTo(self.pointslist[0])
    #             for pt in self.pointslist[1:]:
    #                 path.lineTo(pt)
    #             path.closeSubpath()

    #         if not path.contains(center):
    #             # 寻找形状内部的点
    #             inside_point = None
    #             min_distance = float('inf')

    #             # 对每个顶点
    #             for vertex in self.pointslist:
    #                 # 在中心点和顶点之间进行二分查找
    #                 start = 0.0
    #                 end = 1.0
    #                 for _ in range(10):  # 10次二分迭代
    #                     mid = (start + end) / 2.0
    #                     test_point = QPointF(
    #                         center.x() + (vertex.x() - center.x()) * mid,
    #                         center.y() + (vertex.y() - center.y()) * mid
    #                     )
    #                     if path.contains(test_point):
    #                         # 计算到原始中心点的距离
    #                         dx = test_point.x() - center.x()
    #                         dy = test_point.y() - center.y()
    #                         distance = dx * dx + dy * dy

    #                         if distance < min_distance:
    #                             min_distance = distance
    #                             inside_point = test_point
    #                         end = mid
    #                     else:
    #                         start = mid

    #             if inside_point:
    #                 center = inside_point
    #             else:
    #                 # 如果没找到内部点，退回到第一个顶点
    #                 center = self.pointslist[0]

    #     return center


    def get_universe_central_point(self):
        """
        计算形状的宇宙中心点,确保中心点位于形状内部。
        如果几何中心不在形状内部,则使用最大内接圆的圆心。
        """
        # 获取初始中心点
        center = self.get_center()

        # 对矩形进行特殊处理
        if self.shape_type == "rectangle" and len(self.pointslist) == 2:
            rect = QtCore.QRectF(self.pointslist[0], self.pointslist[1])
            if not rect.contains(center):
                center = QPointF(rect.center())
        else:
            # 对多边形和旋转矩形使用路径检查
            path = QtGui.QPainterPath()
            if len(self.pointslist) > 0:
                path.moveTo(self.pointslist[0])
                for pt in self.pointslist[1:]:
                    path.lineTo(pt)
                path.closeSubpath()

            if not path.contains(center):
                # 使用最大内接圆方法查找中心点
                center = self._find_largest_inscribed_circle_center(path)

        return center

    def _find_largest_inscribed_circle_center(self, path):
        """
        使用距离变换找到形状的最大内接圆圆心
        """
        # 获取边界框
        bbox = path.boundingRect()
        if bbox.width() == 0 or bbox.height() == 0:
            return self.pointslist[0] if self.pointslist else QPointF(0, 0)
        
        # 创建栅格化的二值图像
        # 使用更高的分辨率以提高精度
        resolution = 200
        width = int(bbox.width()) + 1
        height = int(bbox.height()) + 1
        scale_x = resolution / max(width, 1)
        scale_y = resolution / max(height, 1)
        scale = min(scale_x, scale_y)
        
        grid_width = int(width * scale) + 2
        grid_height = int(height * scale) + 2
        
        # 创建二值图像
        binary_image = np.zeros((grid_height, grid_width), dtype=np.uint8)
        
        # 填充形状内部
        for y in range(grid_height):
            for x in range(grid_width):
                # 将栅格坐标转换回实际坐标
                real_x = bbox.left() + x / scale
                real_y = bbox.top() + y / scale
                point = QPointF(real_x, real_y)
                
                if path.contains(point):
                    binary_image[y, x] = 1
        
        # 如果没有内部点,返回第一个顶点
        if not binary_image.any():
            return self.pointslist[0] if self.pointslist else QPointF(0, 0)
        
        # 计算距离变换
        distance_map = distance_transform_edt(binary_image)
        
        # 找到距离最大的点(最大内接圆的圆心)
        max_dist_idx = np.unravel_index(np.argmax(distance_map), distance_map.shape)
        
        # 转换回实际坐标
        center_x = bbox.left() + max_dist_idx[1] / scale
        center_y = bbox.top() + max_dist_idx[0] / scale
        
        return QPointF(center_x, center_y)
    def convert_to_point_shape(self):
        if self.shape_type == "point":
            return
        if self.shape_type not in ["polygon", "rectangle", "rotated_rectangle"]:
            return
        # 获取宇宙中心点
        center = self.get_universe_central_point()

        # 转换为 point 类型
        self.shape_type = "point"
        self.pointslist = [center]
        self._dirty = True  # 标记为需要重绘

        return True  # 返回转换成功标志

######################################################################
# 关于rotated_rectangle的缩放，计算，以及handle_position的确定
# Regarding the scaling, calculation and determination of handle_position of rotated_rectangle
######################################################################
    def scale_rotated_rectangle(self, anchor_index, moving_point, fixed_point, minimum_size=1.0):
        """
        通过拖动锚点实现对旋转矩形的缩放
        anchor_index: 被拖动的顶点索引
        moving_point: 当前鼠标位置
        fixed_point: 固定的对角点位置
        """
        # 获取旋转角度（逆时针为正）
        angle_rad = np.deg2rad(-self.rotated_angle)
        cos_angle = np.cos(-angle_rad)
        sin_angle = np.sin(-angle_rad)

        # 将 moving_point 和 fixed_point 转换到未旋转的局部坐标系
        def to_local(point):
            x = point.x() - fixed_point.x()
            y = point.y() - fixed_point.y()
            local_x = x * cos_angle - y * sin_angle
            local_y = x * sin_angle + y * cos_angle
            return local_x, local_y

        moving_local = to_local(moving_point)
        previous_local = to_local(self.pointslist[anchor_index])

        # 计算新的矩形尺寸
        width = max(abs(moving_local[0]), minimum_size)
        height = max(abs(moving_local[1]), minimum_size)
        sign_x = -1 if moving_local[0] < 0 or (moving_local[0] == 0 and previous_local[0] < 0) else 1
        sign_y = -1 if moving_local[1] < 0 or (moving_local[1] == 0 and previous_local[1] < 0) else 1

        # 确定矩形的四个顶点（未旋转，局部坐标系）
        local_points = [
            QPointF(0, 0),
            QPointF(sign_x * width, 0),
            QPointF(sign_x * width, sign_y * height),
            QPointF(0, sign_y * height),
        ]

        # 将局部坐标系下的顶点变换回全局坐标系，应用旋转和平移
        transform = QtGui.QTransform()
        transform.translate(fixed_point.x(), fixed_point.y())
        transform.rotate(-self.rotated_angle)

        new_points = [transform.map(pt) for pt in local_points]

        self.pointslist = new_points

    def get_rotation_handle_position(self):
        """
        获取旋转控制点的位置，放置在形状外部。
        确保旋转控制点始终位于外部，并且连接线不穿过形状内部。
        """
        # 内联计算宽度和高度
        xs = [p.x() for p in self.pointslist]
        width = max(xs) - min(xs)

        ys = [p.y() for p in self.pointslist]
        height = max(ys) - min(ys)

        if len(self.pointslist) != 4:
            return QtCore.QPointF(0, 0)

        # 获取四个顶点
        p0, p1, p2, p3 = self.pointslist

        # 计算中心点
        center = self.get_center()

        # 计算顶部边（p0-p1）的中心点
        top_center = (p0 + p1) * 0.5

        # 计算边的向量
        edge_vector = np.array([p1.x() - p0.x(), p1.y() - p0.y()])
        edge_angle_rad = np.arctan2(edge_vector[1], edge_vector[0])

        # 计算法线方向，确保指向外部
        normal_angle_rad = edge_angle_rad - np.pi / 2  # 逆时针旋转90度

        # 计算形状的旋转中心到边中心的向量
        to_edge = np.array([top_center.x() - center.x(), top_center.y() - center.y()])
        to_edge_norm = to_edge / np.linalg.norm(to_edge)

        # 确保法线方向与到边向量一致
        if np.dot(to_edge_norm, [np.cos(normal_angle_rad), np.sin(normal_angle_rad)]) < 0:
            normal_angle_rad += np.pi  # 反向

        # 使用固定距离，不依赖形状尺寸
        handle_distance = max(width, height) * 0.15 + 15

        # 计算控制点位置
        handle_x = top_center.x() + handle_distance * np.cos(normal_angle_rad)
        handle_y = top_center.y() + handle_distance * np.sin(normal_angle_rad)

        return QtCore.QPointF(handle_x, handle_y)

    def rotate_rotated_rectangle(self, angle_diff):
        """
        旋转形状
        """
        center = self.get_center()
        transform = QtGui.QTransform()
        transform.translate(center.x(), center.y())
        transform.rotate(angle_diff)
        transform.translate(-center.x(), -center.y())
        self.pointslist = [transform.map(p) for p in self.pointslist]
        self.sync_rotated_angle()

    def sync_rotated_angle(self):
        if getattr(self, 'shape_type', None) == 'rotated_rectangle' and len(self.pointslist) == 4:
            if all(isinstance(p, QPointF) for p in self.pointslist):
                self.rotated_angle = rectangle_angle(self.pointslist)

    def calculate_minimum_rotated_rectangle(self, minimum_size=1.0):
        try:
            rect = minimum_area_rectangle(self.pointslist)
        except ValueError:
            return None
        center, (width, height), angle = rect
        rect = (center, (max(width, minimum_size), max(height, minimum_size)), angle)
        return Shape(label=(self.label or '') + 'MER', classnum=self.classnum,
                     pointslist=[QPointF(float(x), float(y)) for x, y in cv2.boxPoints(rect)],
                     shape_type='rotated_rectangle', group_id=self.group_id,
                     scale_factor=self.scale_factor)

######################################################################
# 通用方法，计算形状的中心点位置
# General Method: Calculating the Center Point Position of a Shape
######################################################################
    def get_center(self):
        """使用 NumPy 优化的中心点计算"""
        if self.shape_type == 'polygon' and len(self.pointslist) >= 3:
            try:
                polygon = Polygon([(p.x(), p.y()) for p in self.pointslist])
                if polygon.is_valid and polygon.area > 0:
                    return QPointF(polygon.centroid.x, polygon.centroid.y)
            except ValueError:
                pass  # Invalid editable contours still need a selection handle.
        points = np.array([[p.x(), p.y()] for p in self.pointslist], dtype=np.float64)
        center = points.mean(axis=0)
        return QPointF(center[0], center[1])

######################################################################
# 绘制方法
# General Method: Calculating the Center Point Position of a Shape
######################################################################
    def paint(self, painter, option, widget=None):
        """
        QGraphicsItem 的 paint 方法实现，负责绘制形状
        """
        if not self.pointslist or not self.visible:
            return

        # 根据缩放因子调整笔宽
        # 使用内部存储的缩放因子
        scale = self.scale_factor
        if scale <= 0:
            scale = 1.0
        appearance = display.current
        if not appearance.auto_scale:
            scale = display.transform_scale(painter.worldTransform())

        pen_width = self.base_pen_width / scale
        pen_width = max(pen_width, 1)  # 确保笔宽不小于1
        control_width = pen_width if appearance.auto_scale else 1.5 / scale
        if not appearance.auto_scale:
            pen_width = (appearance.point_outline_width if self.shape_type == 'point' else appearance.line_width) / scale
        pen_color = self.get_color_by_classnum(self.classnum)
        pen = QtGui.QPen(pen_color, pen_width, display.LINE_STYLES[appearance.line_style]
                         if self.shape_type != 'point' else QtCore.Qt.SolidLine)
        if self.shape_type in ('line', 'rotated_rectangle'):
            control_pen = QtGui.QPen(pen_color, control_width, QtCore.Qt.SolidLine)

        if self._selected:
            brush_color = QtGui.QColor(pen_color)
            brush_color.setAlpha(128)
            brush = QtGui.QBrush(brush_color, QtCore.Qt.SolidPattern)
        else:
            brush = QtGui.QBrush(QtCore.Qt.NoBrush)

        painter.setPen(pen)
        painter.setBrush(brush)

        if self._show_group_id and self.group_id is not None:
            # print(f"绘制 group_id: {self.group_id}, scale_factor: {self.scale_factor}")
            center_pt = self.get_center()
            center_pt = QPointF(center_pt.x(),center_pt.y())
            font = painter.font()
            fontsize=14
            font.setPointSize(int(max(min(fontsize / self.scale_factor, 64), 8)))# 字体大小8-24
            painter.setFont(font)
            painter.drawText(center_pt, str(self.group_id))

        # 绘制形状
        try:
            if self.shape_type == 'rectangle' and len(self.pointslist) == 2:
                rect = QtCore.QRectF(self.pointslist[0], self.pointslist[1])
                painter.drawRect(rect)
            elif self.shape_type == 'polygon' and len(self.pointslist) > 2:
                polygon = self.cached_polygon()
                painter.drawPolygon(polygon)
            elif self.shape_type == 'line' and len(self.pointslist) == 2:
                # 绘制线段
                p1, p2 = self.pointslist
                painter.drawLine(p1, p2)

                midpoint_size = 6 / scale
                midpoint = self.get_center()
                painter.setPen(control_pen)
                painter.drawEllipse(midpoint, midpoint_size, midpoint_size)

            elif self.shape_type == 'rotated_rectangle' and len(self.pointslist) == 4:
                polygon = self.cached_polygon()
                painter.drawPolygon(polygon)
                handle_pos = self.get_rotation_handle_position()
                # 获取第一条边的中心点
                p0, p1, p2, p3 = self.pointslist
                edge_center = (p0 + p1) * 0.5
                # 绘制从边中心到旋转控制点的实线
                line = QtCore.QLineF(edge_center, handle_pos)
                painter.setPen(control_pen)
                painter.drawLine(line)
                painter.setPen(control_pen)
                painter.setBrush(brush)
                handle_size = 6 / scale
                painter.drawEllipse(handle_pos, handle_size, handle_size)

            elif self.shape_type == 'point' and len(self.pointslist) == 1:
                # 绘制点形状 - 新增的代码
                center = self.pointslist[0]
                # 使点的大小足够明显，并随缩放调整
                point_size = int(max(self.base_point_size * 1.5 / scale, 8))
                if not appearance.auto_scale:
                    # Diameter denotes the outer marker extent, including its outline.
                    width = min(appearance.point_outline_width, appearance.point_diameter)
                    pen.setWidthF(width / scale)
                    pen.setCapStyle(QtCore.Qt.FlatCap)
                    # A thick outline can cover all of a tiny marker's fill.
                    # Preserve selection feedback there, and on open cross strokes.
                    if self._selected and (width >= appearance.point_diameter / 2
                                           or appearance.point_style == 'cross'):
                        selected_color = QColor(pen_color)
                        selected_color.setAlpha(128)
                        pen.setColor(selected_color)
                    painter.setPen(pen)
                    point_size = max(0., (appearance.point_diameter - width) / (2 * scale))
                
                fill_color = QColor(255, 255, 255, 80)  # 与顶点相同的填充颜色

                # 选中状态使用填充色，非选中状态只绘制轮廓
                if self._selected:
                    painter.setBrush(brush)
                elif appearance.auto_scale:
                    # 非选中状态轮廓加粗，增加可见性
                    thicker_pen = QtGui.QPen(pen_color, int(pen_width * 1.5), QtCore.Qt.SolidLine)
                    painter.setPen(thicker_pen)
                    
                style = appearance.point_style
                if not appearance.auto_scale and point_size == 0:
                    painter.setPen(QtCore.Qt.NoPen)
                    painter.setBrush(brush if self._selected else QtGui.QBrush(pen_color))
                    point_size = appearance.point_diameter / (2 * scale)
                if style == 'circle':
                    painter.drawEllipse(center, point_size, point_size)
                elif style == 'square':
                    painter.drawRect(QRectF(center.x()-point_size, center.y()-point_size, 2*point_size, 2*point_size))
                else:
                    if self._selected:
                        painter.drawEllipse(center, point_size / 2, point_size / 2)
                    cross_pen = QtGui.QPen(pen if not appearance.auto_scale else painter.pen())
                    cross_pen.setCapStyle(QtCore.Qt.FlatCap)
                    painter.setPen(cross_pen)
                    radius = display.point_radius(scale, self.base_point_size)
                    painter.drawLine(QPointF(center.x()-radius, center.y()), QPointF(center.x()+radius, center.y()))
                    painter.drawLine(QPointF(center.x(), center.y()-radius), QPointF(center.x(), center.y()+radius))
                painter.setBrush(QtGui.QBrush(fill_color, QtCore.Qt.SolidPattern))

        except Exception as e:
            print(f"绘制形状时出错: {e}")

        # 安全绘制顶点
        try:
            if self.shape_type != 'point':
                self.draw_vertices(painter, scale)
        except Exception as e:
            print(f"绘制顶点时出错: {e}")

    def draw_vertices(self, painter, scale):
        # 添加安全检查，确保 scale 不会太小
        if scale <= 0.0001:  # 设定一个最小阈值
            scale = 0.1
        # 如果是多边形且未被选中，直接返回，不绘制任何顶点
        if self.shape_type == 'polygon' and not self.selected:
            return  # 未选中的多边形不绘制顶点，无论是否有悬停点

        # 绘制顶点的逻辑
        try:
            for index, point in enumerate(self.pointslist):
                if point is None or not isinstance(point, QPointF):
                    continue  # 跳过无效点


                fill_color = QColor(255, 255, 255, 80)  # 添加此行初始化fill_color

                if index == self.hovered_point_index:
                    fill_color = QColor(255, 255, 255, 20)
                    try:
                        outline_color = self.get_color_by_classnum(self.classnum)
                    except Exception:
                        outline_color = QtGui.QColor('black')  # 出错时使用黑色

                    point_size = int(self.base_point_size * 2 / scale)  # 悬停时放大
                    if not display.current.auto_scale:
                        point_size = self.base_point_size * 2 / scale

                    # 绘制正方形点
                    half_size = int(point_size / 2)
                    if not display.current.auto_scale:
                        half_size = point_size / 2
                    rect = QtCore.QRectF(point.x() - half_size, point.y() - half_size, point_size, point_size)
                    painter.setPen(QtGui.QPen(outline_color, 4 / scale))
                    painter.setBrush(QtGui.QBrush(fill_color, QtCore.Qt.SolidPattern))
                    painter.drawRect(rect)
                    continue  # 跳过绘制圆形

                try:
                    outline_color = self.get_color_by_classnum(self.classnum)
                except Exception as e:
                    outline_color = QtGui.QColor('black')  # 出错时使用黑色

                point_size = self.base_point_size  / scale
                point_size = int(max(point_size, 2 / scale))  # 确保点大小不小于最小值
                if not display.current.auto_scale:
                    point_size = max(self.base_point_size, 2) / scale

                # 绘制顶点轮廓
                painter.setPen(QtGui.QPen(outline_color, 1 / scale))
                painter.setBrush(QtGui.QBrush(fill_color, QtCore.Qt.SolidPattern))
                painter.drawEllipse(point, point_size, point_size)
        except Exception as e:
            print(f"绘制顶点时出错: {e}")

######################################################################
# 以下方法是对应各个形状的特征提取方法，其被入口文件中直接调用同
# The following methods are the feature extraction methods corresponding to each shape,
# and they are directly called in the entry file.
######################################################################
    @measured
    def feature_extraction_polygon(self, scale_info=None):
        try:
            polygon, center_coordinates, Eccentricity = polygon_moments(self.pointslist)
            A, P = polygon.area, polygon.length
            # Shapely retains float64 coordinates throughout minimum rectangle/hull geometry.
            rectangle = np.array(polygon.minimum_rotated_rectangle.exterior.coords[:-1])
            edges = np.linalg.norm(np.roll(rectangle, -1, axis=0)-rectangle, axis=1)
            Length, Width = float(max(edges)), float(min(edges))
            Circularity = (4 * np.pi * A) / (P ** 2) if P != 0 else 0
            hull = polygon.convex_hull
            ACH, PCH = hull.area, hull.length

            # 计算 Roundness
            Roundness = (4 * np.pi * A) / (PCH ** 2) if PCH != 0 else 0

            # 计算 Convexity
            Convexity = PCH / P if P != 0 else 0

            # 计算 Solidity
            Solidity = A / ACH if ACH != 0 else 0

                    # 计算中心点
            center = QPointF(*center_coordinates)
            center_point = f"({center.x()}, {center.y()})"
                # 如果有比例尺信息，进行换算
            if scale_info:
                scale = scale_info.get('scale', 1)
                unit = scale_info.get('unit', 'pixel')
                A *= (scale ** 2)
                P *= scale
                Length *= scale
                Width *= scale
                ACH *= (scale ** 2)
                PCH *= scale
                self.unit = unit  # 保存单位信息
            else:
                scale = 1.0
                self.unit = 'pixel'
                # 准备特征数据
            self.feature_results = {}

            # 存储计算结果
            self.feature_results = {
                'Label': self.label,
                'Group ID': self.group_id,
                'Area': A,
                'Perimeter': P,
                'MER Length': Length,
                'MER Width': Width,
                'Circularity': Circularity,
                'Eccentricity': Eccentricity,
                'ACH': ACH,
                'PCH': PCH,
                'Roundness': Roundness,
                'Convexity': Convexity,
                'Solidity': Solidity,
                'Center Point': center_point
            }
        except Exception as e:
            print(f"特征提取发生错误：{e}")
            self.feature_results = {}  # 使用空字典而不是'Error'字符串

    @measured
    def feature_extraction_line(self, scale_info=None):
        """
        提取所有可见线形状的特征并显示在 MeasuredResultsDock 的 Line 选项卡中。
        
        参数:
            scale_info (dict): 包含比例尺信息，例如 {'scale': 1.0}
        """
        if scale_info:
            scale = scale_info.get('scale', 1.0)
            self.unit= scale_info.get('unit', 'pixel')
        else:
            scale = 1.0
            self.unit = 'pixel'

        # 准备特征数据
        self.feature_results = {}
        # 获取所有可见的线形状
        if self.shape_type == 'line':
        

       
            start_point = self.pointslist[0]
            end_point = self.pointslist[1]
        
            # 计算长度并考虑比例尺
            dx = end_point.x() - start_point.x()
            dy = end_point.y() - start_point.y()
            length = np.hypot(dx, dy) * scale
            
            # 计算角度（与水平线的夹角，单位为度）
            angle_rad = np.arctan2(dy, dx)
            angle_deg = np.degrees(angle_rad)

                    # 计算中心点
            center = self.get_center()
            center_point = f"({center.x()}, {center.y()})"

            
        self.feature_results= {
            'Label': self.label,
            'Group ID': self.group_id,
            'Length': float(length),
            'Start Point': f"({start_point.x()}, {start_point.y()})",
            'End Point': f"({end_point.x()}, {end_point.y()})",
            'Angle': float(angle_deg),
            'Center Point': center_point  # 添加中心点
        }

    @measured
    def feature_extraction_rotated_rectangle(self, scale_info=None):
        """
        提取旋转矩形的特征并显示在 MeasuredResultsDock 的 Rotated Rectangle 选项卡中。
        
        参数:
            scale_info (dict): 包含比例尺信息，例如 {'scale': 1.0, 'unit': 'cm'}
        """
        if scale_info:
            scale = scale_info.get('scale', 1.0)
            self.unit= scale_info.get('unit', 'pixel')
        else:
            scale = 1.0
            self.unit = 'pixel'
            # 准备特征数据
        self.feature_results = {}

        if self.shape_type == 'rotated_rectangle':
            # 将 pointslist 转换为 NumPy 数组
            vertices = self.pointslist 
            coords = np.array([[p.x(), p.y()] for p in vertices], dtype=np.float64)

            # 计算相邻顶点之间的距离
            width = np.linalg.norm(coords[0] - coords[1]) * scale
            length = np.linalg.norm(coords[1] - coords[2]) * scale
            Length = max(width, length)  # MER 长
            Width = min(width, length)   # MER 宽

            # 计算纵横比
            aspect_ratio = float(Length / Width) if Width != 0 else 0
            self.sync_rotated_angle()
            angle = self.rotated_angle
            
            # 计算中心点
            center = self.get_center()
            center_point = f"({center.x()}, {center.y()})"

          

            # 存储计算结果
        self.feature_results = {
                    'Label': self.label,
                    'Group ID': self.group_id,
                    'Width': float(Width),
                    'Length': float(Length),
                    'Aspect Ratio': aspect_ratio,
                    'Angle': float(angle),
                    'Center Point': center_point  # 添加中心点
                }
        
    @measured
    def feature_extraction_rectangle(self, scale_info=None):
        """
        提取矩形的特征并存储在 feature_results 中。
        
        指标:
            'Label', 'Group ID',
            'Width', 'Length',
            'Aspect Ratio', 
            'Center Point'
        
        参数:
            scale_info (dict): 包含比例尺信息，例如 {'scale': 1.0, 'unit': 'cm'}
        """

        # 应用比例尺信息
        if scale_info:
            scale = scale_info.get('scale', 1.0)
            self.unit = scale_info.get('unit', 'pixel')
        else:
            scale = 1.0
            self.unit = 'pixel'
                # 准备特征数据
        self.feature_results = {}

        # 检查形状类型和可见性
        if self.shape_type == 'rectangle':
            # 获取两个点：top_left 和 bottom_right
  

            top_left, bottom_right = self.pointslist

            # 提取坐标
            x1, y1 = top_left.x(), top_left.y()
            x2, y2 = bottom_right.x(), bottom_right.y()

            # 计算宽度和长度
            width = abs(x2 - x1) * scale
            length = abs(y2 - y1) * scale
            Length = max(width, length)  # MER 长
            Width = min(width, length)   # MER 宽
          #  print(Length, Width)
            # 计算纵横比
            aspect_ratio = float(Length / Width) if Width != 0 else 0

            # 计算中心点
            center = self.get_center()
            center_point = f"({center.x()}, {center.y()})"

            # 存储计算结果
            self.feature_results = {
                'Label': self.label,
                'Group ID': self.group_id,
                'Width': float(Width),
                'Length': float(Length),
                'Aspect Ratio': aspect_ratio,
                'Center Point': center_point  # 添加中心点
            }

    @measured
    def feature_extraction_point(self, scale_info=None):
        """
        提取矩形的特征并存储在 feature_results 中。
        
        指标:
            'Label', 'Group ID',
            'X', 'Y',
 
        """
    # 准备特征数据
        self.feature_results = {}
        # 检查形状类型和可见性
        if self.shape_type == 'point':
            # 获取两个点：top_left 和 bottom_right

            X= self.pointslist[0].x()
            Y= self.pointslist[0].y()


          
            # 存储计算结果
            self.feature_results = {
                'Label': self.label,
                'Group ID': self.group_id,
                'X': float(X),
                'Y': float(Y),
                
            }

#################################################################################
#Virtual functions (subclass overrides parent class methods) and implicit methods
#虚函数与隐式方法
#################################################################################
    def boundingRect(self):
        """Return the bounding rectangle of the shape.
        This method is required by QGraphicsItem."""
        if not self.pointslist:
            return QRectF()
        # 添加一些边距以确保能完全容纳绘制内容
        return self.visual_bounds()

    def update_shape(self):
        """通知需要更新，但只重绘此形状"""
        self.prepareGeometryChange()  # 通知 Qt 几何形状变化
        self._dirty = True
        # 使用 QGraphicsItem 的 update 方法，只会重绘此项
        QGraphicsItem.update(self)  # 明确调用基类方法

    def shape(self):
        """返回形状的精确路径，用于精确碰撞检测"""
        if not display.current.auto_scale and self.shape_type in ('point', 'line') and self.pointslist:
            scale = max(self.scale_factor, 1e-6)
            key = (self.shape_type, scale, display.revision)
            cached = self._geometry_cache.get('hit_path')
            if cached and cached[0] == key:
                return QtGui.QPainterPath(cached[1])
            path = QtGui.QPainterPath()
            if self.shape_type == 'point':
                radius = display.point_hit_radius(scale, self.base_point_size)
                path.addEllipse(self.pointslist[0], radius, radius)
            elif len(self.pointslist) == 2:
                path.moveTo(self.pointslist[0]); path.lineTo(self.pointslist[1])
                stroker = QtGui.QPainterPathStroker(); stroker.setWidth(10 / scale)
                path = stroker.createStroke(path)
            self._geometry_cache['hit_path'] = (key, path)
            return QtGui.QPainterPath(path)
        cache_key = ('path', self.shape_type, self.base_point_size)
        if cache_key in self._geometry_cache:
            return QtGui.QPainterPath(self._geometry_cache[cache_key])
        path = QtGui.QPainterPath()

        if not self.pointslist:
            return path

        if self.shape_type == 'polygon' and len(self.pointslist) > 2:
            polygon = self.cached_polygon()
            path.addPolygon(polygon)
        elif self.shape_type == 'rectangle' and len(self.pointslist) == 2:
            rect = QRectF(self.pointslist[0], self.pointslist[1])
            path.addRect(rect)
        elif self.shape_type == 'rotated_rectangle' and len(self.pointslist) == 4:
            polygon = self.cached_polygon()
            path.addPolygon(polygon)
        elif self.shape_type == 'line' and len(self.pointslist) == 2:
            # 为线创建一个有一定宽度的路径
            p1, p2 = self.pointslist
            line = QtCore.QLineF(p1, p2)
            path.moveTo(p1)
            path.lineTo(p2)

            # 添加一些厚度使之更容易选择
            stroker = QtGui.QPainterPathStroker()
            stroker.setWidth(10)
            path = stroker.createStroke(path)

        elif self.shape_type == 'point' and len(self.pointslist) == 1:
            # 为点创建一个小圆形路径
            center = self.pointslist[0]
            path.addEllipse(center, self.base_point_size * 2, self.base_point_size * 2)

        self._geometry_cache[cache_key] = path
        return QtGui.QPainterPath(path)

    def __eq__(self, other):
        if not isinstance(other, Shape):
            return False
        return (self.label == other.label and
                self.classnum == other.classnum and
                self.shape_type == other.shape_type and
                self.group_id == other.group_id and
                len(self.pointslist) == len(other.pointslist) and
                all(self_point.x() == other_point.x() and self_point.y() == other_point.y()
                    for self_point, other_point in zip(self.pointslist, other.pointslist)))

    def __hash__(self):
        return hash(self.group_id)
