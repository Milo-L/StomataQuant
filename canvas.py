# canvas.py
from PIL.FtexImagePlugin import Format
from PyQt5 import QtCore, QtGui, QtWidgets
from PyQt5.QtCore import QPointF, QLineF
from PyQt5.QtGui import QColor
from matplotlib import scale
from shape import Shape
import numpy as np
import numba



USE_NUMBA = True  # 默认启用 Numba


def check_numba():
    """检查 Numba 是否可用，如果出现错误则禁用"""
    try:
        @numba.jit(nopython=True, cache=True)
        def test_func(x, y):
            return x + y
        test_func(1.0, 2.0)  # 运行一次，触发编译
        return True
    except Exception as e:
        print(f"Numba Self-check failed: {e}")
        return False
######################################################################
# 全局函数，使用Numba加速计算
# Global function, using Numba to accelerate computation
######################################################################
# 带有错误处理的 Numba 函数 | A Numba function with error handling
def _calculate_distance_numba(x1, y1, x2, y2):
    """计算两点之间的距离，自动在 Numba 失败时降级"""
    global USE_NUMBA
    if USE_NUMBA:
        try:
            return _calculate_distance_numba_accelerated(x1, y1, x2, y2)
        except Exception as e:
            print(f"Numba acceleration failed in _calculate_distance_numba: {e}")
            USE_NUMBA = False
            print("Switched to pure Python implementation for distance calculation")
    # 降级到纯 Python 实现
    dx = x2 - x1
    dy = y2 - y1
    return np.sqrt(dx*dx + dy*dy)

def _point_in_polygon_numba(point_x, point_y, vertices_x, vertices_y):
    """判断点是否在多边形内，自动在 Numba 失败时降级"""
    global USE_NUMBA
    if USE_NUMBA:
        try:
            return _point_in_polygon_numba_accelerated(point_x, point_y, vertices_x, vertices_y)
        except Exception as e:
            print(f"Numba acceleration failed in _point_in_polygon_numba: {e}")
            USE_NUMBA = False
            print("Switched to pure Python implementation for point-in-polygon test")
    
    # 降级到纯 Python 实现
    n = len(vertices_x)
    inside = False
    j = n - 1
    for i in range(n):
        if ((vertices_y[i] > point_y) != (vertices_y[j] > point_y)):
            denominator = vertices_y[j] - vertices_y[i]
            if abs(denominator) > 1e-10:  # 避免除以接近零的值
                x_intersect = (vertices_x[j] - vertices_x[i]) * (point_y - vertices_y[i]) / denominator + vertices_x[i]
                if point_x < x_intersect:
                    inside = not inside
        j = i
    return inside

# 定义 Numba 加速版本的函数
if USE_NUMBA:
    try:
        @numba.jit(nopython=True, cache=True)
        def _calculate_distance_numba_accelerated(x1, y1, x2, y2):
            dx = x2 - x1
            dy = y2 - y1
            return np.sqrt(dx*dx + dy*dy)

        @numba.jit(nopython=True, cache=True)
        def _point_in_polygon_numba_accelerated(point_x, point_y, vertices_x, vertices_y):
            n = len(vertices_x)
            inside = False
            j = n - 1
            for i in range(n):
                if ((vertices_y[i] > point_y) != (vertices_y[j] > point_y)):
                    denominator = vertices_y[j] - vertices_y[i]
                    if abs(denominator) > 1e-10:  # 避免除以接近零的值
                        x_intersect = (vertices_x[j] - vertices_x[i]) * (point_y - vertices_y[i]) / denominator + vertices_x[i]
                        if point_x < x_intersect:
                            inside = not inside
                j = i
            return inside
    except Exception as e:
        print(f"Failed to define Numba functions: {e}")
        USE_NUMBA = False

######################################################################
# Canvas
######################################################################
class Canvas(QtWidgets.QGraphicsObject):
    shapeSelected = QtCore.pyqtSignal(list)
    shapeCreated = QtCore.pyqtSignal(Shape)
    shapesChanged = QtCore.pyqtSignal()

    def __init__(self, image_size, scale_factor=1.0, parent=None):
        super(Canvas, self).__init__(parent)
        self.mode = 'edit'  # 可选值：'edit' 或 'create'
        self.shapes = []
        self.selected_shape = []  # 存储多个选中的形状
        self.hovered_shape = None
        self.moving_shape = False
        self.start_point_at_create_mode = None  # 用于记录鼠标的起始位置：在创建模式时使用
        self.dragging_point = False
        self.drag_start_pos = QtCore.QPointF()
        self.image_size = image_size
        self.scale_factor = scale_factor  # 添加缩放因子
        self.create_shape_type = None  # 当前要创建的形状类型
        self.current_shape = None  # 正在绘制的形状
        self.drawing = False  # 是否正在绘制
        self.rotating = False  # 是否正在旋转"旋转矩形“
        self.scaling_rotated_rectangle = False  # 是否正在缩放“旋转矩形”
        self.undo_stack = [] # 维护一个操作栈，用于保存历史状态
        #self.current_cursor = QtCore.Qt.ArrowCursor  # 缓存当前光标状态
        self.setAcceptHoverEvents(True)
        self.setFlag(QtWidgets.QGraphicsItem.ItemIsSelectable, True)
        # 确保 Canvas 能接收场景更新
        self.setFlag(QtWidgets.QGraphicsItem.ItemSendsScenePositionChanges, True)
        self.current_mouse_pos = None
        self.auto_label = None
        self.auto_label_shape_type = None
        self.apply_label_to_shape_type = False
        self.apply_label_to_all_shapes = False
        self.rotated_rect_stage = 0  # 0: 未开始, 1: 已按下第一个点, 2: 已确定第一条边

#######################################################################################
# 基本方法，多在入口文件中被调用
# The basic method is mostly called in the entry file.
#######################################################################################
    def add_shape(self, shape):
        """添加形状到场景中,被duplicate_shape调用"""
        """Add shapes to the scene, which is called by duplicate_shape"""
        if shape not in self.shapes:
            self.shapes.append(shape)
            # 确保新添加的形状与画布使用相同的缩放因子
            if hasattr(shape, 'set_scale_factor'):
                shape.set_scale_factor(self.scale_factor)

            self.shapesChanged.emit()

    def remove_shape(self, shape):
        """从场景中安全地移除形状，清理所有引用"""
        "Remove shapes from the scene safely and clear all references."
        if shape in self.shapes:
            # 从列表中移除
            self.shapes.remove(shape)
            # 安全地从场景中移除
            try:
                scene = self.scene()
                if scene and shape.scene() == scene:
                    scene.removeItem(shape)
                elif shape.scene() is None:
                    # 如果形状已经不在任何场景中，则无需移除
                    pass
                else:
                    print(f"警告：形状{shape}不属于当前场景")
            except Exception as e:
                print(f"从场景移除形状时出错: {e}")
            # 清除所有可能的引用
            if shape == self.hovered_shape:
                self.hovered_shape = None

            if shape in self.selected_shape:
                self.selected_shape.remove(shape)
            # 清除其他引用
            if hasattr(self, 'scaling_shape') and self.scaling_shape == shape:
                self.scaling_shape = None
                self.scaling_rotated_rectangle = False

            if hasattr(self, 'rotating_shape') and self.rotating_shape == shape:
                self.rotating_shape = None
                self.rotating = False

            # 通知界面更新
            self.shapesChanged.emit()

    def boundingRect(self):
        width, height = self.image_size.width(), self.image_size.height()
        return QtCore.QRectF(0, 0, width, height)

    def set_scale_factor(self, scale):
        self.scale_factor = scale
        for shape in self.shapes:
            if hasattr(shape, 'set_scale_factor'):
                shape.set_scale_factor(scale)


    def set_mode(self, mode):
        self.mode = mode
        if self.mode == 'edit': #编辑模式
            self.create_shape_type = None
            self.current_shape = None

        else: # 创建模式
            self.selected_shape = []
            self.current_shape = None
            self.drawing = False
            self.create_shape_type = None

#######################################################################################
# 关键方法，获取鼠标附近的形状或点的索引，整个鼠标事件的基础
# The key method is to obtain the index of the shape or point near the mouse cursor.
# the basis for the entire mouse event.
#######################################################################################
    def get_shape_at_pos(self, pos, tolerance=5):
        if pos is None:
            return None, None
        pos_x, pos_y = pos.x(), pos.y()
        for shape in reversed(self.shapes):
            if shape.visible:
                if shape.shape_type == 'rotated_rectangle':
                    handle_pos = shape.get_rotation_handle_position()
                    is_near, _ = self.is_point_near_handle(pos, handle_pos, tolerance=10)
                    if is_near:
                        return shape, 'rotation_handle'

                    if self.is_pos_inside_shape(shape, pos):
                        return shape, 'inside'

                    closest_vertex = self.find_closest_vertex(pos, shape.pointslist, tolerance=10)
                    if closest_vertex >= 0:
                        return shape, closest_vertex

                elif shape.shape_type == 'polygon':
                    if shape.selected:
                        closest_vertex = self.find_closest_vertex(pos, shape.pointslist, tolerance)
                        if closest_vertex >= 0:
                            return shape, closest_vertex

                    if self.is_pos_inside_shape(shape, pos):
                        return shape, None

                elif shape.shape_type == 'rectangle':
                    closest_vertex = self.find_closest_vertex(pos, shape.pointslist, tolerance)
                    if closest_vertex >= 0:
                        return shape, closest_vertex

                    if self.is_pos_inside_shape(shape, pos):
                        return shape, None

                elif shape.shape_type == 'line' and len(shape.pointslist) == 2:
                    midpoint = shape.get_center()
                    is_near_mid, _ = self.is_point_near_handle(pos, midpoint, tolerance)
                    if is_near_mid:
                        return shape, 'mid'

                    closest_vertex = self.find_closest_vertex(pos, shape.pointslist, tolerance)
                    if closest_vertex >= 0:
                        return shape, closest_vertex

                elif shape.shape_type == 'point' and len(shape.pointslist) == 1:
                    is_near, _ = self.is_point_near_handle(pos, shape.pointslist[0], tolerance)
                    if is_near:
                        return shape, 'point'
        return None, None
        
    def is_point_near_handle(self, pos, handle_pos, tolerance=5):
        """检查点是否接近控制点"""
        if pos is None or handle_pos is None:
            return False, float('inf')
            
        dist = _calculate_distance_numba(pos.x(), pos.y(), handle_pos.x(), handle_pos.y())
        return dist <= tolerance, dist

    def find_closest_vertex(self, pos, vertices, tolerance=5):
        """查找最近的顶点"""
        if not vertices:
            return -1
            
        min_dist = float('inf')
        closest_idx = -1
        
        vertices_x = np.array([p.x() for p in vertices])
        vertices_y = np.array([p.y() for p in vertices])
        
        for i in range(len(vertices)):
            dist = _calculate_distance_numba(pos.x(), pos.y(), vertices_x[i], vertices_y[i])
            if dist <= tolerance and (closest_idx == -1 or dist < min_dist):
                min_dist = dist
                closest_idx = i
                
        return closest_idx

    def is_close_enough(self, p1, p2, tolerance=5):
        """判断两点是否足够接近"""
        if p1 is None or p2 is None:
            return False
        return _calculate_distance_numba(p1.x(), p1.y(), p2.x(), p2.y()) <= tolerance

    @staticmethod
    def is_pos_inside_shape(shape, pos):
        """使用Numba加速的点在形状内判断"""
        try:
            if shape is None or pos is None:
                return False
                
            if shape.shape_type in ['polygon', 'rotated_rectangle']:
                # 确保形状有有效的点列表
                if not shape.pointslist or len(shape.pointslist) < 3:
                    return False
                
                 # 提取顶点坐标为NumPy数组，增加安全检查    
                try:
                    # 确保 pointslist 中的元素都是有效的 QPointF 对象
                    valid_points = [p for p in shape.pointslist if isinstance(p, QPointF)]
                    if len(valid_points) < 3:
                        return False
                        
                    vertices_x = np.array([p.x() for p in valid_points])
                    vertices_y = np.array([p.y() for p in valid_points])
                    
                    # 确保数组非空且长度匹配
                    if len(vertices_x) == 0 or len(vertices_x) != len(vertices_y):
                        return False
                        
                    # 使用Numba加速函数判断
                    return _point_in_polygon_numba(pos.x(), pos.y(), vertices_x, vertices_y)
                
                except Exception as e:
                    print(f"Error in point extraction: {e}")
                    return False

            elif shape.shape_type == 'rectangle' and len(shape.pointslist) == 2:
                # 矩形的判断保持不变
                if None in shape.pointslist:
                    return False
                rect = QtCore.QRectF(shape.pointslist[0], shape.pointslist[1])
                return rect.contains(pos)
            else:
                return False
        except Exception as e:
            print(f"Error in is_pos_inside_shape: {e}")
            return False

    def which_line_closest(self, shape, point, epsilon=3):
        """查找最接近的线段"""
        # 对于多边形，如果未选中，直接返回
        if shape.shape_type == 'polygon' and not shape.selected:
            return -1

        # 确保有足够的点来形成线段
        if not shape.pointslist or len(shape.pointslist) < 2:
            return -1

        min_distance = float('inf')
        closest_index = -1
        n = len(shape.pointslist)
        pos_x, pos_y = point.x(), point.y()

        for i in range(n):
            start_idx = (i - 1) % n
            p1 = shape.pointslist[start_idx]
            p2 = shape.pointslist[i]

            # 计算向量
            v1_x = p2.x() - p1.x()
            v1_y = p2.y() - p1.y()
            v2_x = pos_x - p1.x()
            v2_y = pos_y - p1.y()
            v3_x = pos_x - p2.x()
            v3_y = pos_y - p2.y()

            # 点积计算
            dot1 = v1_x * v2_x + v1_y * v2_y
            dot2 = -v1_x * v3_x - v1_y * v3_y

            # 距离计算
            if dot1 < 0:
                # 点到p1的距离
                dist = _calculate_distance_numba(pos_x, pos_y, p1.x(), p1.y())
            elif dot2 < 0:
                # 点到p2的距离
                dist = _calculate_distance_numba(pos_x, pos_y, p2.x(), p2.y())
            else:
                # 点到线段的垂直距离
                cross_product = abs(v2_x * v1_y - v2_y * v1_x)
                v1_length = np.sqrt(v1_x * v1_x + v1_y * v1_y)
                if v1_length < 1e-10:  # 避免除零
                    dist = _calculate_distance_numba(pos_x, pos_y, p1.x(), p1.y())
                else:
                    dist = cross_product / v1_length

            # 更新最近距离
            if dist <= epsilon and dist < min_distance:
                min_distance = dist
                closest_index = i

        return closest_index

#######################################################################################
# 关键方法，控制整个canvas的绘制逻辑
# Key Method: Control the Drawing Logic of the Entire Canvas
#######################################################################################
    def paint(self, painter, option, widget=None):
        # 设置抗锯齿
        painter.setRenderHint(QtGui.QPainter.Antialiasing)
        try:
            # 首先绘制所被标记为 dirty 的可见形状
            for shape in self.shapes:
                if shape.visible and not shape._dirty:
                    try:
                        # 直接调用每个形状的paint方法，传递正确的参数
                        shape.paint(painter, option, widget)
                    except Exception as e:
                        print(f"绘制常规形状时出错: {e}")
                        
            # 然后单独绘制所有被标记为 dirty 的形状
            for shape in self.shapes:
                if shape.visible and shape._dirty:
                    try:
                        shape.paint(painter, option, widget)
                        shape._dirty = False  # 重置 dirty 标记
                    except Exception as e:
                        print(f"绘制脏形状时出错: {e}")

            # 绘制当前正在创建的形状
            if self.current_shape and self.drawing:
                try:
                    self.current_shape.paint(painter, option, widget)
                    self.draw_creation_guides(painter)
                except Exception as e:
                    print(f"绘制创建中的形状时出错: {e}")

            # 绘制悬停效果
            if self.mode == 'edit' and self.hovered_shape and self.hovered_shape.visible:
                try:
                    self.draw_hover_effect(painter, self.hovered_shape)
                except Exception as e:
                    print(f"绘制悬停效果时出错: {e}")
                    
        except Exception as e:
            print(f"Canvas.paint 方法出错: {e}")

    def draw_hover_effect(self, painter, shape):
        """单独绘制形状的悬停效果"""
        if not shape or not shape.visible or shape._show_points:
            return
        pen_color = QColor(255, 255, 255, 64)
        
        pen_width = max(int(2 / self.scale_factor), 1) 
        pen = QtGui.QPen(pen_color, pen_width, QtCore.Qt.SolidLine)
        painter.setPen(pen)
        brush_color = QtGui.QColor(pen_color)
        brush_color.setAlpha(64)  # 50% 透明度填充
        brush = QtGui.QBrush(brush_color, QtCore.Qt.SolidPattern)
        painter.setBrush(brush)
        if shape.shape_type == 'rectangle' and len(shape.pointslist) == 2:
            rect = QtCore.QRectF(shape.pointslist[0], shape.pointslist[1])
            painter.drawRect(rect)
        elif shape.shape_type == 'polygon' and len(shape.pointslist) > 2:
            polygon = QtGui.QPolygonF(shape.pointslist)
            painter.drawPolygon(polygon)
        elif shape.shape_type == 'line' and len(shape.pointslist) == 2:
            painter.drawLine(shape.pointslist[0], shape.pointslist[1])
        elif shape.shape_type == 'rotated_rectangle' and len(shape.pointslist) == 4:
            polygon = QtGui.QPolygonF(shape.pointslist)
            painter.drawPolygon(polygon)  # 绘制旋转矩形

    def draw_creation_guides(self, painter):

        if not self.current_shape or self.create_shape_type is None:
            return
        """绘制创建形状时的辅助线和预览"""
        pen = QtGui.QPen(QtGui.QColor(255, 255, 255),  max(int(2/self.scale_factor), 1) , QtCore.Qt.DashLine)
        painter.setPen(pen)

        if self.create_shape_type == 'rectangle' and len(self.current_shape.pointslist) == 2:
            rect = QtCore.QRectF(self.current_shape.pointslist[0], self.current_shape.pointslist[1])
            painter.drawRect(rect)
 
        elif self.create_shape_type == 'rotated_rectangle':
            if self.rotated_rect_stage == 1 and len(self.current_shape.pointslist) == 1:
                # 第一阶段：绘制拖动线段
                pen.setWidth(max(int(2 / self.scale_factor), 1) )
                painter.setPen(pen)
                if self.current_mouse_pos:
                    painter.drawLine(self.current_shape.pointslist[0], self.current_mouse_pos)
                    
                    # 高亮显示第一个点
                    point_size = max(int(6/self.scale_factor), 2)  # 确保是整数
                    painter.setBrush(QtGui.QBrush(QtGui.QColor(255, 255, 255)))
                    painter.drawEllipse(self.current_shape.pointslist[0], point_size, point_size)
            
            elif self.rotated_rect_stage == 2 and len(self.current_shape.pointslist) >= 4:
                # 第二阶段：绘制整个旋转矩形预览
                polygon = QtGui.QPolygonF(self.current_shape.pointslist)
                
                # 使用更明显的样式绘制预览
                pen = QtGui.QPen(QtGui.QColor(255, 255, 255), max(int(2/self.scale_factor), 1), QtCore.Qt.DashLine)
                painter.setPen(pen)
                painter.setBrush(QtGui.QBrush(QtGui.QColor(0, 0, 0, 60)))
                painter.drawPolygon(polygon)
                # 绘制四个角
                point_size = max(int(6/self.scale_factor), 2)  # 确保是整数
                painter.setBrush(QtGui.QBrush(QtGui.QColor(0, 0, 0, 60)))
                for point in self.current_shape.pointslist:
                    painter.drawEllipse(point, point_size, point_size)
                
        

        elif self.create_shape_type == 'polygon':            
     
            if len(self.current_shape.pointslist) >= 1:
                # 绘制已有的线段
                points = self.current_shape.pointslist
                if len(points) > 1:
                    for i in range(len(points) - 1):
                        painter.drawLine(points[i], points[i + 1])
                    if self.current_mouse_pos:
                        painter.drawLine(points[-1], self.current_mouse_pos)
                
                # 绘制所有点
                point_size = 4/self.scale_factor  # 更大的点尺寸
                painter.setBrush(QtGui.QBrush(QtGui.QColor(255, 255, 255, 180)))
                for point in points:
                    painter.drawEllipse(point, point_size, point_size)

        elif self.create_shape_type == 'line' and len(self.current_shape.pointslist) == 1:
            if self.current_mouse_pos:
                painter.drawLine(self.current_shape.pointslist[0], self.current_mouse_pos)

    def set_selected_shapes(self, shapes):
        # 找出状态将要发生变化的形状
        shapes_to_update = []

        # 标记将被取消选择的形状
        for s in self.shapes:
            was_selected = s.selected
            is_selected = s in shapes

            if was_selected != is_selected:
                s._dirty = True
                shapes_to_update.append(s)
                s.selected = is_selected

        self.selected_shape = shapes
        self.shapeSelected.emit(shapes)

        # 如果有形状状态变化，更新相关区域
        if shapes_to_update:
            for s in shapes_to_update:
                s.update_shape()

######################################################################
# 关于形状创建的一系列方法
# A Series of Methods for Creating Shapes
######################################################################
    def create_polygon(self):
        """创建多边形模式"""
        self.mode = 'create'
        self.create_shape_type = 'polygon'
        self.current_shape = Shape(shape_type='polygon',scale_factor=self.scale_factor)
        self.drawing = False
        self.save_state()

    def create_rotated_rectangle(self):
        """创建旋转矩形模式"""
        self.mode = 'create'
        self.create_shape_type = 'rotated_rectangle'
        self.current_shape = Shape(shape_type='rotated_rectangle',scale_factor=self.scale_factor)
        self.drawing = False
        self.save_state()

    def create_rectangle(self):
        """创建矩形模式"""
        self.mode = 'create'
        self.create_shape_type = 'rectangle' 
        self.current_shape = Shape(shape_type='rectangle',scale_factor=self.scale_factor)
        self.drawing = False
        self.save_state()

    def create_line(self):
        """创建线条模式"""
        self.mode = 'create'
        self.create_shape_type = 'line'
        self.current_shape = Shape(shape_type='line',scale_factor=self.scale_factor)
        self.drawing = False
        self.save_state()

    def create_point(self):
        """创建点模式"""
        self.mode = 'create'
        self.create_shape_type = 'point'
        self.current_shape = Shape(shape_type='point',scale_factor=self.scale_factor)
        self.drawing = False
        self.save_state()

    def finish_shape(self):
        """完成形状创建"""
        if self.current_shape:
            self.shapes.append(self.current_shape)
            self.shapeCreated.emit(self.current_shape)
            self.save_state()
            self.current_shape = None
            self.drawing = False
            self.create_shape_type = self.create_shape_type
            self.shapesChanged.emit()
            self.update()

###############################################
############ 撤销回退机制的实现
############ the revocation/undo mechanism
###############################################
    def save_state(self):
        """保存当前形状状态以支持撤销操作，手动创建新的形状对象而不是使用deepcopy"""
        try:
            # 创建形状的简化表示，只包含可安全序列化的数据
            shapes_state = []
            for shape in self.shapes:
                try:
                    # 安全地收集有效点
                    valid_points = []
                    for p in shape.pointslist:
                        if p is not None and isinstance(p, QPointF):
                            try:
                                valid_points.append(QPointF(p.x(), p.y()))
                            except Exception as e:
                                print(f"无法复制点: {e}")
                                continue

                    # 检查形状是否有效
                    if not valid_points:
                        print(f"跳过无效形状: 没有有效的点")
                        continue

                    # 确保多边形至少有3个点，或者其他形状符合要求
                    if (shape.shape_type == 'polygon' and len(valid_points) < 3) or \
                            (shape.shape_type == 'rectangle' and len(valid_points) != 2) or \
                            (shape.shape_type == 'line' and len(valid_points) != 2) or \
                            (shape.shape_type == 'rotated_rectangle' and len(valid_points) != 4) or \
                            (shape.shape_type == 'point' and len(valid_points) != 1):
                        print(f"跳过无效形状: {shape.shape_type} 点数量不正确")
                        continue

                    # 为每个形状创建一个新实例
                    new_shape = Shape(
                        label=shape.label,
                        classnum=shape.classnum,
                        pointslist=valid_points,
                        shape_type=shape.shape_type,
                        group_id=shape.group_id

                    )
                    # 复制必要的其他属性
                    new_shape.visible = shape.visible
                    new_shape._selected = shape._selected
                    new_shape.rotated_angle = shape.rotated_angle
                    new_shape._show_group_id = shape._show_group_id
                    new_shape.feature_results = shape.feature_results
                    new_shape.scale_factor = shape.scale_factor

                    # 添加到状态列表
                    shapes_state.append(new_shape)
                except Exception as e:
                    print(f"处理形状时出错: {e}")
                    continue  # 跳过这个形状

            # 存储状态
            self.undo_stack.append(shapes_state)

            # 限制撤销栈大小
            if len(self.undo_stack) > 4:
                self.undo_stack.pop(0)

        except Exception as e:
            print(f"保存状态时出错: {e}")
            # 错误处理 - 可能需要清空撤销栈以避免进一步问题
            self.undo_stack = []

    def undo(self):
        """安全地恢复到上一个保存的状态"""
        if not self.undo_stack:
            return

        try:
            # 恢复上一个状态
            previous_shapes = self.undo_stack.pop()
            scene = self.scene()

            if not scene:
                print("警告：当前画布没有关联场景")
                return

            # 清除当前状态
            self.selected_shape = []
            self.hovered_shape = None

            
            # 清除场景中的所有形状
            for shape in self.shapes.copy():
                try:
                    if shape.scene() == scene:
                        scene.removeItem(shape)
                    self.shapes.remove(shape)
                except Exception as e:
                    print(f"从场景移除形状时出错: {e}")
            
            # 确保形状列表为空
            self.shapes.clear()
            
            # 为每个保存的形状创建新的形状对象
            for saved_shape in previous_shapes:
                try:
                    # 创建新的形状对象，保持原有属性
                    new_shape = Shape(
                        label=saved_shape.label,
                        classnum=saved_shape.classnum,
                        pointslist=[QPointF(p.x(), p.y()) for p in saved_shape.pointslist],
                        shape_type=saved_shape.shape_type,
                        group_id=saved_shape.group_id
                    )
                    
                    # 复制其他属性
                    new_shape.visible = saved_shape.visible
                    new_shape._selected = saved_shape._selected
                    new_shape.rotated_angle = saved_shape.rotated_angle
                    new_shape._show_group_id = saved_shape._show_group_id
                    new_shape.feature_results = saved_shape.feature_results
                    
                    # 只添加到列表和场景，不设置父项
                    self.shapes.append(new_shape)
                    # scene.addItem(new_shape)
                    # 移除这一行: new_shape.setParentItem(self)
                except Exception as e:
                    print(f"恢复形状时出错: {e}")
                    continue
                    
            # 重置交互状态
            self.dragging_point = False
            self.moving_shape = False
            self.rotating = False
            self.scaling_rotated_rectangle = False
            
            # 更新界面
            self.shapesChanged.emit()
            self.update()
                        
        except Exception as e:
            print(f"撤销操作出错: {e}")
            self.undo_stack = []
            self.update()

###############################################
############ 关于鼠标事件代码==========Hover
###############################################
    def hoverMoveEvent(self, event):

        pos = event.pos()  # 获取鼠标当前位置。
        if self.mode == 'create' and self.create_shape_type == 'rotated_rectangle':
            if self.rotated_rect_stage == 2 :
                # 第二阶段：实时更新鼠标位置，以便计算预览矩形
                p1 = self.current_shape.pointslist[0]
                p2 = self.current_shape.pointslist[1]
    
                # 计算旋转矩形的另外两个点
                prevertex_c, prevertex_d = self.calculate_rotated_rectangle(p1, p2, pos)
                
                if prevertex_c and prevertex_d:  # 确保计算结果有效
                    # 确保列表有足够长度容纳4个点
                    while len(self.current_shape.pointslist) < 4:
                        self.current_shape.pointslist.append(None)
                    # 现在可以安全地更新点
                    self.current_shape.pointslist[2] = prevertex_c
                    self.current_shape.pointslist[3] = prevertex_d

            self.update()  # 请求重绘
            super(Canvas, self).hoverMoveEvent(event)
            return
        
        elif self.mode =='edit':
            pos = event.pos()  # 获取鼠标当前位置。
            cursor = QtCore.Qt.ArrowCursor  # 初始化光标为箭头光标。
            hovered = False  # 初始化悬停状态为 False
            self.hovered_shape = None  # 初始化悬停的形状为 None
            self.hovered_point_index = None  # 初始化悬停的点索引为 None

            # 首先重置所有形状的悬停点索引
            for s in self.shapes:
                s.hovered_point_index = None

            # 检查是否有选中的形状
            has_selected_shapes = len(self.selected_shape) > 0

            try:
                # 如果有选中的形状，只检查这些形状
                if has_selected_shapes:
                    shape, index = None, None
                    # 只检查选中的形状
                    for selected in self.selected_shape:
                        if not selected.visible:
                            continue

                        # 使用自定义方法检查点或区域是否在这个选中形状上
                        if selected.shape_type == 'rotated_rectangle':
                            handle_pos = selected.get_rotation_handle_position()
                            is_near, _ = self.is_point_near_handle(pos, handle_pos, 8)
                            if is_near:
                                shape, index = selected, 'rotation_handle'
                                break

                        closest_vertex = self.find_closest_vertex(pos, selected.pointslist, 5)
                        if closest_vertex >= 0:
                            shape, index = selected, closest_vertex
                            break

                        if self.is_pos_inside_shape(selected, pos):
                            shape, index = selected, 'inside'
                            break
                else:
                    # 如果没有选中形状，则检查所有形状
                    shape, index = self.get_shape_at_pos(pos)
            except Exception as e:
                print(f"Error in get_shape_at_pos: {e}")
                shape, index = None, None

            # 处理找到的形状
            if shape and shape.visible:
                if shape.shape_type == 'rotated_rectangle' and shape.visible:
                    self.hoverMoveEvent_rotated_rectangle(event)

                elif shape.shape_type in ["polygon", "rectangle"] and shape.visible:
                    if index is not None:
                        # 处理点悬停
                        self.hovered_shape = shape
                        self.hovered_point_index = index
                        shape.hovered_point_index = index
                        cursor = QtCore.Qt.CrossCursor
                        shape.update_shape()
                        hovered = True
                    else:
                        if self.is_pos_inside_shape(shape, pos):
                            self.hovered_shape = shape
                            self.hovered_point_index = None
                            shape.hovered_point_index = None
                            shape.update_shape()
                            hovered = True

                elif shape.shape_type == "line":
                    if index != "mid":
                        self.hovered_point_index = index
                        shape.hovered_point_index = index
                        shape.update_shape()
                        hovered = True
                    else:
                        pass

                elif shape.shape_type == "point":
                    if index == "point":
                        self.hovered_shape = shape
                        cursor = QtCore.Qt.CrossCursor
                        shape.update_shape()
                        hovered = True

            self.setCursor(QtGui.QCursor(cursor))
            self.update()# 必须得不能注释
            super(Canvas, self).hoverMoveEvent(event)
            return
        

        else:
            super(Canvas, self).hoverMoveEvent(event)
            return    

    def hoverMoveEvent_rotated_rectangle(self, event):
        pos = event.pos()
        cursor = QtCore.Qt.ArrowCursor
        hovered = False
        self.hovered_shape = None
        self.hovered_point_index = None
        shape, index = self.get_shape_at_pos(pos) # 获取鼠标位置附近的形状和点索引    
        if shape is None:
            return
        if shape.visible and index:
            hovered = True
            self.hovered_shape = shape
            shape.hovered_point_index = None
            self.hovered_point_index = None
            if index not in ['rotation_handle', 'inside']:
                self.hovered_point_index = index
                shape.hovered_point_index = index
        self.update()# 必须得不能注释

###############################################
############ 关于鼠标事件代码===========Press
###############################################
    def calculate_rotated_rectangle(self,point_a, point_b, mouse_pos):
        """
        计算旋转矩形的四个顶点
        
        参数:
        point_a, point_b -- 矩形的第一条边的两个端点
        mouse_pos -- 当前鼠标位置，决定矩形的高度
        
        返回:
        point_c, point_d -- 矩形的另外两个顶点
        """
        # 计算线段AB的向量和长度
        ab_vector = QtCore.QPointF(point_b.x() - point_a.x(), point_b.y() - point_a.y())
        ab_length = np.sqrt(ab_vector.x() ** 2 + ab_vector.y() ** 2)
        
        if ab_length < 1e-6:  # 防止除零错误
            return None, None
            
        # 计算AB的单位方向向量
        unit_ab = QtCore.QPointF(ab_vector.x() / ab_length, ab_vector.y() / ab_length)
        
        # 计算垂直于AB的单位向量 (逆时针旋转90度)
        perp_unit_ab = QtCore.QPointF(-unit_ab.y(), unit_ab.x())
        
        # 计算从点A到点M的向量
        am_vector = QtCore.QPointF(mouse_pos.x() - point_a.x(), mouse_pos.y() - point_a.y())
        
        # 计算点M到线AB的垂直距离（带符号）
        height = am_vector.x() * perp_unit_ab.x() + am_vector.y() * perp_unit_ab.y()
        
        # 计算矩形的另外两个点 (保证是矩形，不是平行四边形)
        point_d = QtCore.QPointF(
            point_a.x() + height * perp_unit_ab.x(),
            point_a.y() + height * perp_unit_ab.y()
        )
        
        point_c = QtCore.QPointF(
            point_b.x() + height * perp_unit_ab.x(),
            point_b.y() + height * perp_unit_ab.y()
        )
        
        return point_c, point_d
    
    def mousePressEvent(self, event):
        self.moving_start_pos = event.pos()
        self.start_point_at_create_mode = event.pos()  # 添加这一行，记录起始位置
 
        if self.mode == 'create':
            self.current_mouse_pos = event.pos()
            self.handle_createmode_mouse_press(event)
        else:
            pos = event.pos()
            clicked_shape, clicked_part = self.get_shape_at_pos(pos, tolerance=8)

            if clicked_shape and clicked_shape.shape_type == 'rotated_rectangle':
                self.handle_editmode_mouse_press_rotated_rectangle(event, clicked_shape, clicked_part)
            elif clicked_shape and clicked_shape.shape_type == 'line':
                self.handle_editmode_mouse_press_line(event, clicked_shape, clicked_part)
            elif clicked_shape and clicked_shape.shape_type == 'point'and clicked_part == 'point':
                self.moving_shape = True
                self.drag_start_pos = pos
                clicked_shape.selected = True
                self.set_selected_shapes([clicked_shape])
            
            else:

                self.handle_editmode_mouse_press(event)
        super(Canvas, self).mousePressEvent(event)





    def handle_createmode_mouse_press(self, event):
        """处理创建模式下的鼠标事件"""
        pos = event.pos()
        if self.create_shape_type == 'rotated_rectangle':
            if event.button() == QtCore.Qt.LeftButton:
                if not self.drawing:  # 第一次按下 - 阶段1开始
                    self.drawing = True
                    self.rotated_rect_stage = 1
                    self.current_shape = Shape(shape_type=self.create_shape_type,scale_factor=self.scale_factor)
                    self.current_shape.pointslist = [pos]
                    self.update()
                    
                elif self.rotated_rect_stage == 2:  # 第二次点击 - 完成旋转矩形
                    # 此时已经在阶段2，鼠标移动已经在预览矩形
                    # 将当前鼠标位置作为确定高度的点
                    p1 = self.current_shape.pointslist[0]
                    p2 = self.current_shape.pointslist[1]
                   
                    # 计算旋转矩形的四个点
                    p3, p4 = self.calculate_rotated_rectangle(p1, p2, pos)
                    self.current_shape.pointslist[2] = p3
                    self.current_shape.pointslist[3] = p4
      
                    
                    # 计算旋转角度
                    edge_vector = QtCore.QLineF(p1, p2)
                    angle = edge_vector.angle()
                    self.current_shape.rotated_angle = angle
                    
                    # 完成形状创建
                    self.finish_shape()
                    self.drawing = False  # 重置状态
                    self.rotated_rect_stage = 0  # 重置阶段

        elif self.create_shape_type == 'rectangle':
            # 原有的矩形创建逻辑保持不变
            if event.button() == QtCore.Qt.LeftButton:
                # 开始绘制
                self.drawing = True
                self.current_shape = Shape(shape_type=self.create_shape_type,scale_factor=self.scale_factor)
                self.current_shape.pointslist = [pos]
                self.update()

        elif self.create_shape_type == 'point':
            if event.button() == QtCore.Qt.LeftButton:

                self.drawing = True
                self.current_shape = Shape(shape_type='point',scale_factor=self.scale_factor)
                self.current_shape.pointslist = [pos]
                self.finish_shape()
                        
        elif self.create_shape_type == 'line':   
            if event.button() == QtCore.Qt.LeftButton:

                self.drawing = True
                self.current_shape = Shape(shape_type='line',scale_factor=self.scale_factor, pointslist=[pos])
                self.update()
    
        elif self.create_shape_type == 'polygon':
            if event.button() == QtCore.Qt.LeftButton:
                if not self.drawing:
                    # 开始绘制第一个点
                    self.drawing = True
                    self.current_shape = Shape(shape_type='polygon',scale_factor=self.scale_factor)  # 添加这行创建新的多边形对象
                    self.current_shape.pointslist.append(pos)
                    self.update()


                else:
                    self.current_shape.pointslist.append(pos)
                    self.update()  # 刷新画布以显示新线
                    
                    # 检查是否与第一个点闭合
                    if len(self.current_shape.pointslist) >= 3:
                        first_point = self.current_shape.pointslist[0]
                        # 判断是否与第一个点足够接近以闭合
                        if self.is_close_enough(pos, first_point, tolerance=8):
                            self.finish_shape()

    def handle_editmode_mouse_press_rotated_rectangle(self, event, clicked_shape, clicked_part):
        pos = event.pos()
        
        if event.button() == QtCore.Qt.LeftButton:
            if clicked_part not in ['rotation_handle', 'inside']  and clicked_shape is not None:
                clicked_shape.selected = True
                self.selected_shape = [clicked_shape]
                self.hovered_point_index = clicked_part
                self.shapeSelected.emit([clicked_shape])
                

                self.scaling_rotated_rectangle = True
                self.scaling_shape = clicked_shape
                self.hovered_point_index = clicked_part
                
                self.scaling_anchor_index = clicked_part
                self.scaling_fixed_index = (clicked_part + 2) % 4  # 对角点索引
                self.scaling_fixed_point = clicked_shape.pointslist[self.scaling_fixed_index]

                self.previous_mouse_pos = pos  # 记录鼠标起始位置
                self.initial_point = clicked_shape.pointslist[clicked_part]  # 记录被拖动顶点的初始位置
                # self.update_rotation_handle(clicked_shape)
                clicked_shape.get_rotation_handle_position()

                # 可在此处添加逻辑，例如更新显示连接线等
            elif clicked_part == 'rotation_handle':
                # 开始旋转
                self.rotation_start_pos = pos
                clicked_shape.selected = True
                self.hovered_shape = clicked_shape
                self.selected_shape = [clicked_shape]
                self.shapeSelected.emit([clicked_shape])
                self.rotating = True
                self.rotating_shape = clicked_shape
                self.rotation_center = clicked_shape.get_center()

                       
            elif clicked_part == 'inside':
                modifiers = event.modifiers()
                ctrl_pressed = modifiers & QtCore.Qt.ControlModifier
                if ctrl_pressed:
                    if clicked_shape in self.selected_shape:
                        # 如果形状已被选中，取消选中
                        self.selected_shape.remove(clicked_shape)
                        clicked_shape.selected = False
                    else:
                        # 添加形状到选中列表
                        self.selected_shape.append(clicked_shape)
                        clicked_shape.selected = True
                    
                    self.set_selected_shapes(self.selected_shape)
                    self.shapeSelected.emit(self.selected_shape)
                else:
                    # 如果未按下 Ctrl 键，清除其他选择，只选择当前形状
                    for s in self.shapes:
                        s.selected = False
                    self.selected_shape = [clicked_shape]
                    clicked_shape.selected = True
                    self.shapeSelected.emit(self.selected_shape)
                
                self.moving_shape = True
                self.drag_start_pos = pos
                self.save_state()
                self.shapesChanged.emit()
                self.setCursor(QtCore.Qt.ClosedHandCursor)
                    
        self.update()

    def handle_editmode_mouse_press_line(self, event, clicked_shape, clicked_part):
        pos=event.pos()
        if event.button() == QtCore.Qt.LeftButton:
            if clicked_shape:
                if isinstance(clicked_part, int):
                    self.selected_shape = [clicked_shape]
                    self.hovered_point_index = clicked_part
                    print(f"##############Clicked on point {clicked_part} of shape {clicked_shape}########")
                    clicked_shape.selected = True
                    
                    self.shapeSelected.emit([clicked_shape])
                    self.setCursor(QtCore.Qt.CrossCursor)
                    self.dragging_point = True
                    self.drag_start_pos = pos
                    self.save_state()
                    self.shapesChanged.emit()
                    self.update()


                elif clicked_part == 'mid':
                    modifiers = event.modifiers()
                    ctrl_pressed = modifiers & QtCore.Qt.ControlModifier
                    if ctrl_pressed:
                        if clicked_shape in self.selected_shape:
                            # 如果形状已被选中，取消选中
                            self.selected_shape.remove(clicked_shape)
                            clicked_shape.selected = False
                        else:
                            # 添加形状到选中列表
                            self.selected_shape.append(clicked_shape)
                            clicked_shape.selected = True
                        self.set_selected_shapes(self.selected_shape)
                        self.shapeSelected.emit(self.selected_shape)
                    else:
                        # 如果未按下 Ctrl 键，清除其他选择，只选择当前形状
                        for s in self.shapes:
                            s.selected = False
                        self.selected_shape = [clicked_shape]
                        clicked_shape.selected = True
                        self.shapeSelected.emit(self.selected_shape)


                    self.moving_shape = True
                    self.drag_start_pos = pos
                    self.save_state()
                    self.shapesChanged.emit()
                    self.setCursor(QtCore.Qt.ClosedHandCursor)
        self.update()
     
    def handle_editmode_mouse_press(self, event):
        pos = event.pos()
        clicked_point_index = None
        clicked_shape = None
        
        if event.button() == QtCore.Qt.LeftButton:
            modifiers = event.modifiers()
            ctrl_pressed = modifiers & QtCore.Qt.ControlModifier
            clicked_shape, clicked_point_index = self.get_shape_at_pos(pos)

            if clicked_shape:
                if clicked_shape.shape_type !='rotated_rectangle':
                    if clicked_point_index is not None:
                        
                        # 进入拖动点模式
                        self.selected_shape = [clicked_shape]
                        self.hovered_point_index = clicked_point_index

                        print(f"Clicked on point {clicked_point_index} of shape {clicked_shape}")
                        clicked_shape.selected = True
                        print(f"Selected shape: {clicked_shape}. Selected: {clicked_shape.selected} from handle_editmode_mouse_press")
                        # self.set_selected_shapes([clicked_shape])
                        self.shapeSelected.emit([clicked_shape])
                        self.setCursor(QtCore.Qt.CrossCursor)
                        self.dragging_point = True
                        self.drag_start_pos = pos
                        self.save_state()
                        self.shapesChanged.emit()
                        self.update()
                        return
                    
                    else:
                        # 2. 检查是否点击在线段上（用于添加点，仅对polygon有效）
                        for shape in reversed(self.shapes):
                            if shape.visible and shape.shape_type == 'polygon' and shape.selected:
                                line_index = self.which_line_closest(shape, pos)
                                
                                if line_index != -1:
                                    shape.add_point(line_index, pos)
                                    shape.selected = True
                                    self.selected_shape = [shape]
                                    self.shapeSelected.emit([shape])
                                    self.save_state()
                                    self.shapesChanged.emit()
                                    shape.update_shape()
                                    return

                        # 3. 检查是否点击在形状内部（用于拖动整个形状）
                        for shape in reversed(self.shapes):
                            if shape.visible and self.is_pos_inside_shape(shape, pos):
                                if ctrl_pressed:
                                    # Ctrl 被按下，进行多选
                                    if shape in self.selected_shape:
                                        # 如果形状已被选中，取消选中
                                        self.selected_shape.remove(shape)
                                        shape.selected = False
                                    else:
                                        # 添加形状到选中列表
                                        self.selected_shape.append(shape)
                                        shape.selected = True
                                    
                                    self.set_selected_shapes(self.selected_shape)
                                    self.shapeSelected.emit(self.selected_shape)
                                    self.save_state()
                                    self.shapesChanged.emit()
                                    self.update()
                                

                                else:
                                    # 未按下 Ctrl，选择单个形状

                                    for s in self.selected_shape:
                                        s.selected = False
                                    self.selected_shape = [shape]
                                    shape.selected = True


                                self.set_selected_shapes(self.selected_shape)
                                self.shapeSelected.emit(self.selected_shape)
                                self.update()

                            # 开始拖动选中的形状
                                if self.selected_shape:
                                    self.moving_shape = True
                                    self.drag_start_pos = pos
                                    self.save_state()
                                    self.shapesChanged.emit()
                                    self.setCursor(QtCore.Qt.ClosedHandCursor)
                                return
                            
                        # 4. 点击空白区域，取消所有选中状态
                        self.set_selected_shapes([])
                        self.shapeSelected.emit([])
            
                        self.update()
                elif clicked_shape.shape_type == 'rotated_rectangle':
                    self.handle_editmode_mouse_press_rotated_rectangle(event, clicked_shape, clicked_point_index)
            else:
                self.set_selected_shapes([])
                self.update()
                return
        elif event.button() == QtCore.Qt.RightButton:
            modifiers = event.modifiers()
            ctrl_pressed = modifiers & QtCore.Qt.ControlModifier
            clicked_shape, _ = self.get_shape_at_pos(pos)
            if not clicked_shape:
                # 右键点击空白区域，无需操作
                self.set_selected_shapes([])
                self.update()
                return
            if clicked_shape.shape_type == 'rotated_rectangle':
                self.handle_editmode_mouse_press_rotated_rectangle(event, clicked_shape, clicked_point_index)
                return
            else:
                if ctrl_pressed:
                    # 按住Ctrl并右键点击，删除多个点
                    self.delete_polygon_multiple_points(pos)
                else:
                    # 正常右键点击，删除单个点
                    self.delete_polygon_single_point(pos)

        super(Canvas, self).mousePressEvent(event)

###############################################
############ 关于右键删除多边形的点是删除单个点还是多个点
############ delete a single point or multiple points by right-clicking a polygon
###############################################
    def get_multiple_points_of_a_polygon_at_pos(self, pos, shape, count_range=(3, 25), radius=10):
        """
        获取多边形上距离指定位置最近的多个点的索引

        参数:
        pos -- 鼠标位置
        shape -- 多边形形状
        count_range -- 要删除的点数量范围（最小值，最大值）
        radius -- 考虑局部密度的半径

        返回:
        要删除的点的索引列表，按距离从近到远排序
        """
        if not shape or shape.shape_type != 'polygon' or len(shape.pointslist) <= 5:
            return []  # 如果不是多边形或者点太少，直接返回空列表

        # 计算所有点到指定位置的距离
        distances = []
        for i, point in enumerate(shape.pointslist):
            dist = _calculate_distance_numba(pos.x(), pos.y(), point.x(), point.y())
            distances.append((i, dist))

        # 按距离排序
        distances.sort(key=lambda x: x[1])

        # 计算局部点密度
        # 计算半径 radius 内的点数量
        points_in_radius = sum(1 for _, dist in distances if dist <= radius)

        # 根据局部密度确定要删除的点数量
        # 局部密度越高，删除的点越多，但在count_range范围内
        min_count, max_count = count_range
        density_factor = min(1.0, points_in_radius / 10.0)  # 假设局部区域内有10个点为高密度

        # 计算要删除的点数量，在count_range范围内
        points_to_remove = int(min_count + density_factor * (max_count - min_count))

        # 限制删除点的数量，不能太多以至于破坏多边形
        max_points_to_remove = max(0, min(points_to_remove, len(shape.pointslist) - 3))  # 至少保留3个点

        # 返回要删除的点的索引列表
        return [idx for idx, _ in distances[:max_points_to_remove]]

    def delete_polygon_multiple_points(self, pos):
        """
        删除多边形上距离指定位置最近的多个点

        参数:
        pos -- 鼠标位置

        返回:
        是否成功删除多个点
        """
        for shape in reversed(self.shapes):
            if shape.visible and shape.shape_type == 'polygon' and shape.selected:
                # 获取要删除的点的索引
                points_to_delete = self.get_multiple_points_of_a_polygon_at_pos(pos, shape)

                if not points_to_delete:
                    return False  # 没有找到要删除的点

                # 按索引从大到小排序，以便删除时不会影响其他索引
                points_to_delete.sort(reverse=True)

                # 删除点
                for idx in points_to_delete:
                    if len(shape.pointslist) > 3:  # 确保多边形至少保留3个点
                        shape.remove_point(idx)
                        shape.update_shape()


                self.save_state()
                self.shapesChanged.emit()
                return True

        return False

    def delete_polygon_single_point(self, pos):
        """删除polygon在指定位置的点"""
        for shape in reversed(self.shapes):
            if shape.visible and shape.shape_type == 'polygon' and shape.selected:
                shape, index = self.get_shape_at_pos(pos, tolerance=10)
                if shape and index is not None:
                    shape.remove_point(index)
                    self.save_state()
                    self.shapesChanged.emit()
                    self.update()
                    return True
        return False

###############################################
############ 关于鼠标事件代码===========Move
###############################################

    
    def mouseMoveEvent(self, event):
        pos = event.pos()  # 确保 pos 在方法一开始就被定义
        self.current_mouse_pos = pos  # 更新当前鼠标位置

        if self.mode == 'create' and self.drawing:
            if self.create_shape_type == 'rectangle':
                if len(self.current_shape.pointslist) == 1:
                    self.current_shape.pointslist.append(pos)
                else:
                    self.current_shape.pointslist[1] = pos
                self.update()
            # 添加旋转矩形的移动预览处理

            elif self.create_shape_type == 'rotated_rectangle':
                if self.rotated_rect_stage == 1 and len(self.current_shape.pointslist) == 1:
                    self.update()  # 触发重绘，显示线段预览


                    
            elif self.create_shape_type == 'line':
               self.current_mouse_pos = event.pos()
               self.update()
            


                
        ################### 编辑模式下 鼠标 运动事件
        elif self.mode == 'edit':
            shapes_to_update = []
            ### 对于旋转矩形的 旋转事件
            if self.rotating and self.rotating_shape:
                # 保存旧状态
                self.rotating_shape._dirty = True
                shapes_to_update.append(self.rotating_shape)
                # 旋转逻辑...
                center = self.rotation_center
                line1 = QLineF(center, self.rotation_start_pos)
                line2 = QLineF(center, pos)
                angle_diff = line2.angle() - line1.angle()
                angle_diff = -angle_diff  # 反转角度增量
                self.rotating_shape.rotate_rotated_rectangle(angle_diff)
                self.rotating_shape.update_shape()  # 只更新当前形状
                # 添加这一行来更新旋转起始位置
                self.rotation_start_pos = pos  # 这样每次移动都会更新参考点

            ### 对于旋转矩形的放缩事件
            elif self.scaling_rotated_rectangle and self.scaling_shape:
                self.scaling_shape._dirty = True
                shapes_to_update.append(self.scaling_shape)
                
                # 缩放逻辑...
                moving_point = pos
                fixed_point = self.scaling_fixed_point
                anchor_index = self.scaling_anchor_index
                self.scaling_shape.scale_rotated_rectangle(anchor_index, moving_point, fixed_point)
                self.scaling_shape.update_shape()  # 只更新当前形状

            ### 对于旋转矩形和其他shape的移动事件
            elif self.moving_shape and self.selected_shape:

                dx = pos.x() - self.moving_start_pos.x()
                dy = pos.y() - self.moving_start_pos.y()

                for shape in self.selected_shape:
                    shape._dirty = True
                    shapes_to_update.append(shape)
                    shape.moveBy(dx, dy)
                    shape._dirty = True
                    shape.update()  # 只更新被移动的形状
                self.moving_start_pos = pos
            ### 对于其他shape的点的拖动事件
            elif self.dragging_point:
                shape = self.selected_shape[0]
                shape._dirty = True
                shapes_to_update.append(shape)
                
                # 更新点位置
                index = self.hovered_point_index
                shape.pointslist[index] = pos
                self.shapesChanged.emit()
                shape._dirty = True
                shape.update()  # 只更新当前形状
            
           
        # 如果有形状需要更新，只更新这些形状
            if shapes_to_update:
                # 标记需要重绘的区域更大一点，确保覆盖完整
                self.update()
            

            
        super(Canvas, self).mouseMoveEvent(event)

####################################################
############ 关于鼠标事件代码===============Release
####################################################
    def mouseReleaseEvent(self, event):
        pos = event.pos()  # 添加这一行，获取鼠标当前位置
        if self.mode == 'create' and self.drawing:
            if self.create_shape_type != 'polygon':
                end_point = event.pos()  # 获取结束位置
                # 定义一个容差，判断鼠标是否有移动
                tolerance = 3  # 允许的最小移动距离
                moved_distance = (end_point - self.start_point_at_create_mode).manhattanLength()

                if moved_distance <= tolerance:
                    # 鼠标没有移动，不创建形状
                    self.current_shape = None  # 重置当前形状
                    self.drawing = False
                    self.update()
                    return  # 直接返回，不执行后续创建逻辑


                if self.create_shape_type == 'rectangle':
                    self.finish_shape()
                    self.drawing = False
                    
                elif self.create_shape_type == 'line':
                    pos = event.pos()
                    self.current_shape.pointslist.append(pos)
                    if len(self.current_shape.pointslist) == 2:
                        self.finish_shape()
                        self.drawing = False
                        
                elif self.create_shape_type == 'rotated_rectangle':
                    if self.rotated_rect_stage == 1:  # 第一阶段鼠标释放，确定第一条边
                        # 检查移动距离是否足够

                        start_point = self.current_shape.pointslist[0]
                        moved_distance = _calculate_distance_numba(
                            start_point.x(), start_point.y(), pos.x(), pos.y())
                        if moved_distance < 5:  # 移动太小，不处理
                            print("移动距离太小，无法确定边长")
                            # 重置状态
                            self.current_shape = None
                            self.drawing = False
                            self.rotated_rect_stage = 0
                            self.update()
                            return
                        
                        # 添加第二个点，完成第一条边的创建
                        self.current_shape.pointslist.append(pos)
                        self.rotated_rect_stage = 2  # 进入第二阶段
                        self.drawing = True
                        self.update()  # 立即更新显示


        elif self.mode == 'edit':
            if event.button() == QtCore.Qt.LeftButton:
                self.scaling_rotated_rectangle = False
                self.hovered_point_index = None
                self.moving_shape = False
                self.rotating = False
                self.setCursor(QtCore.Qt.ArrowCursor)

            if self.dragging_point:
                self.dragging_point = False
                self.scaling_rotated_rectangle = False
                self.scaling_shape = None
                self.hovered_point_index = None
                self.scaling_anchor_index = None
                self.scaling_fixed_index = None
                self.scaling_fixed_point = None
                self.setCursor(QtCore.Qt.ArrowCursor)
                self.update()

        super(Canvas, self).mouseReleaseEvent(event)

###############################################
############ 关于鼠标事件代码===========DoubleClick
###############################################
    def mouseDoubleClickEvent(self, event):
        """处理双击事件"""
        if self.mode == 'create' and self.create_shape_type == 'polygon':
            if self.drawing and len(self.current_shape.pointslist) >= 3:
                # 将当前点与第一个点连接，形成闭合多边形
                self.current_shape.pointslist.append(self.current_shape.pointslist[0])
                self.finish_shape()
