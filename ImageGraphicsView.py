#################### 功能实现--打开后的图片缩放
from PyQt5.QtWidgets import QGraphicsView, QGraphicsScene,QGraphicsPixmapItem
from PyQt5.QtCore import pyqtSignal, Qt, QRectF
from PyQt5.QtGui import QPixmap,QImageReader
from canvas import Canvas

#ImageGraphicsView 的类，该类继承自 QGraphicsView，用于显示和缩放图像
class ImageGraphicsView(QGraphicsView):
    zoomChanged = pyqtSignal(int) # 定义一个 zoomChanged 信号，用于在缩放比例发生变化时发射信号
    mousePositionChanged = pyqtSignal(int, int)
    pixelValueChanged = pyqtSignal(int, int, int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setScene(QGraphicsScene(self)) # 创建一个新的 QGraphicsScene 并将其设置为视图的场景
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)# 设置变换锚点为鼠标位置
        self.setResizeAnchor(QGraphicsView.AnchorUnderMouse)# 设置调整大小的锚点为鼠标位置
        self.setStyleSheet("background: transparent; border: none;")
        self.current_zoom = 100
        self.shapes = []
        self.original_pixmap_size = None
        self.pixmap_item = None
        self.dragging = False  # 初始化 dragging 标志
        self.canvas = None  # 初始化为 None

    def load_image(self, file_path):
        try:
            with open(file_path, 'rb') as f:
                data = f.read()
        except Exception as e:
            print(f"Unable to read the content of the file:{e} from ImageGraphicsView.load_image")  # 调试信息
            return
        
        print(f"Try to open the file: {file_path} from ImageGraphicsView.load_image")  # 调试信息
        reader = QImageReader(file_path)
        if reader.canRead():
            image = reader.read()
            pixmap = QPixmap.fromImage(image)
            if pixmap.isNull():
                print(f"Error loading image:{file_path} from ImageGraphicsView.load_image")  # 调试信息
                return
        else:
            print(f"Error loading image:{file_path} from ImageGraphicsView.load_image_else_part")  # 调试信息
            return

        self.set_pixmap(pixmap)

        # 创建 Canvas 并设置大小与图像一致
        image_size = pixmap.size()
        if self.canvas:
            self.scene().removeItem(self.canvas)
        self.canvas = Canvas(image_size)
        self.scene().addItem(self.canvas)

        # 确保 Canvas 在顶部
        self.canvas.setZValue(1)
        self.pixmap_item.setZValue(0)


    def get_shapes(self):
        return self.shapes
    
    def resizeEvent(self, event):
        super().resizeEvent(event)
        # 调整 Canvas 的边界以匹配场景
        if self.canvas:
            self.canvas.update()
        else:
            print("Canvas is None during resizeEvent")  # 调试信息

    def set_pixmap(self, pixmap):
        print("set_pixmap called")  # 调试信息
        # 移除现有的 pixmap_item（如果存在）
        if self.pixmap_item:# 如果存在运行下面的
            print("Removing existing pixmap_item")  # 调试信息
            self.scene().removeItem(self.pixmap_item)
            self.pixmap_item = None

        # 添加新的 pixmap_item
        self.pixmap_item = self.scene().addPixmap(pixmap)
        self.pixmap_item.setZValue(0)  # 图像在 Canvas 之下
        print("New pixmap_item added")  # 调试信息

        # 设置场景矩形为图像的实际大小
        self.scene().setSceneRect(QRectF(pixmap.rect())) 
        # 重置视图变换，以取消之前的任何缩放或旋转
        self.resetTransform()
           # 设置当前缩放比例为 100%
        self.current_zoom = 100
        self.zoomChanged.emit(self.current_zoom)
            # 确保图像加载完成后进行适应视口
        self.fit_to_view_custom()


        # 设置场景矩形
        rect_obj = pixmap.rect()
        print(f"pixmap.rect() type: {type(rect_obj)}")  # 调试信息
        try:
            rect = QRectF(rect_obj)  # 使用 QRectF 的构造函数进行转换
        except Exception as e:
            print(f"Error converting QRect to QRectF: {e}")
            rect = QRectF(rect_obj.x(), rect_obj.y(), rect_obj.width(), rect_obj.height())

        print(f"Setting scene rect to: {rect} (Type: {type(rect)})")  # 调试信息
        self.scene().setSceneRect(rect)
        # self.fitInView(self.sceneRect(), Qt.KeepAspectRatio)
        self.original_pixmap_size = pixmap.size()
        print("set_pixmap completed")  # 调试信息
        
    ### 更新鼠标运动位置，在主窗口中返回信息
    def mouseMoveEvent(self, event):
        super().mouseMoveEvent(event)
        try:
            # 获取当前鼠标位置在场景中的坐标
            pos = self.mapToScene(event.pos())
            x, y = int(pos.x()), int(pos.y())

            # 发射鼠标位置变化的信号（始终发射）
            self.mousePositionChanged.emit(x, y)

            # 初始化像素值
            pixel_value = None  # 用于传递给信号的像素值

            # 获取像素值并发射信号
            if self.pixmap_item:
                pixmap = self.pixmap_item.pixmap()
                if not pixmap.isNull():
                    image = pixmap.toImage()
                    if 0 <= x < image.width() and 0 <= y < image.height():
                        color = image.pixelColor(x, y)
                        r, g, b = color.red(), color.green(), color.blue()
                        pixel_value = (r, g, b)
                    else:
                        # 鼠标在图像范围外
                        pixel_value = None
            else:
                # 没有图像
                pixel_value = None

            # 发射像素值变化的信号
            if pixel_value is not None:
                self.pixelValueChanged.emit(*pixel_value)
            else:
                # 传递特殊值，例如 -1，表示无效
                self.pixelValueChanged.emit(-1, -1, -1)
        except Exception as e:
            print(f"Error in mouseMoveEvent: {e}")
    
    ### 定义窗口放缩事件ctrl+鼠标滚轮 或者 ctrl+键盘 进行缩放
    def wheelEvent(self, event):
        if event.modifiers() == Qt.ControlModifier:
            zoom_in_factor = 1.1
            zoom_out_factor = 1 / zoom_in_factor

            if event.angleDelta().y() > 0:
                self.zoom_in()
            else:
                self.zoom_out()
        else:
            super().wheelEvent(event)

    def keyPressEvent(self, event):
        if event.modifiers() & Qt.ControlModifier:
            if event.key() in (Qt.Key_Plus, Qt.Key_Equal, Qt.KeypadModifier | Qt.Key_Plus):
                self.zoom_in()
            elif event.key() in (Qt.Key_Minus, Qt.Key_Underscore, Qt.KeypadModifier | Qt.Key_Minus):
                self.zoom_out()
        else:
            super().keyPressEvent(event)

    def zoom_in(self):
        zoom_in_factor = 1.05
        new_zoom = self.current_zoom * zoom_in_factor
        new_zoom = min(new_zoom, 1000)
        self.apply_zoom(new_zoom)

    def zoom_out(self):
        zoom_out_factor = 1 / 1.05
        new_zoom = self.current_zoom * zoom_out_factor
        new_zoom = max(new_zoom, 10)
        self.apply_zoom(new_zoom)

     

    def apply_zoom(self, new_zoom):
        """
        应用新的缩放比例而不重置当前的变换，以避免图像位置偏移。
        """
        if new_zoom < 10:
            new_zoom = 10
        elif new_zoom > 1000:
            new_zoom = 1000

        scale_factor = new_zoom / self.current_zoom
        self.scale(scale_factor, scale_factor)
        self.current_zoom = new_zoom
        
        # 自动同步 Canvas 的缩放因子
        if self.canvas:
            self.canvas.set_scale_factor(new_zoom / 100.0)
        
        self.zoomChanged.emit(int(self.current_zoom))
        
    def fit_to_view_custom(self):
        if self.pixmap_item:
            # 使用 fitInView 自动调整图像大小，保持纵横比
            self.fitInView(self.pixmap_item, Qt.KeepAspectRatio)
            
            # 获取当前的缩放比例
            transform = self.transform()
            scale_factor = transform.m11()  # 假设横向和纵向缩放相同
            self.current_zoom = int(scale_factor * 100)
            
            # 发射缩放变化信号
            self.zoomChanged.emit(self.current_zoom)