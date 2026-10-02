from measurements import finite_numeric

import os
import json
import subprocess
import sys
from macos_paths import macos_output_dir
import tempfile
from pathlib import Path
from PyQt5.QtCore import QThread, pyqtSignal
import torch
import gc
import time
import threading
import copy
from types import SimpleNamespace
from PyQt5.QtCore import QPointF
from task_support import OperationCancelled, check_cancelled
from safe_io import available_output_path, source_suffix

_PREDICTION_LOCK = threading.Lock()
_HEATMAP_LOCK = threading.Lock()


class SerializedPrediction:
    def __init__(self, path, value):
        self.path = path
        self.value = value

    def to_json(self):
        return self.value


def run_model_subprocess(config, canceled, worker_script=None):
    """Stop a blocked native prediction by terminating its isolated process."""
    check_cancelled(canceled)
    output_dir = config.get('output_dir')
    if output_dir:
        os.makedirs(output_dir, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.prediction.', dir=output_dir) as temporary:
        config = dict(config)
        if config['kind'] == 'segmentation':
            params = dict(config['params'])
            params['project'] = temporary
            params['name'] = 'prediction'
            config['params'] = params
        request = Path(temporary) / 'request.json'
        response = Path(temporary) / 'response.json'
        request.write_text(json.dumps(config), encoding='utf-8')
        worker_script = worker_script or str(Path(__file__).with_name('inference_worker.py'))
        flags = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
        if sys.platform == 'darwin' and getattr(sys, 'frozen', False):
            if worker_script != str(Path(__file__).with_name('inference_worker.py')):
                raise ValueError('Custom worker scripts require a Python interpreter.')
            worker_args = [sys.executable, '--stomataquant-worker', str(request), str(response)]
        else:
            worker_args = [sys.executable, '-B', worker_script, str(request), str(response)]
        process = subprocess.Popen(worker_args,
                                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                   creationflags=flags)
        try:
            while process.poll() is None:
                if canceled():
                    raise OperationCancelled('Prediction canceled')
                time.sleep(.05)
            check_cancelled(canceled)
            if not response.exists():
                raise RuntimeError(f'Prediction process exited with status {process.returncode}.')
            result = json.loads(response.read_text(encoding='utf-8'))
            if result.get('error'):
                raise RuntimeError(result['error'])
            if config['kind'] == 'segmentation':
                generated = Path(temporary) / 'prediction'
                if generated.exists():
                    while True:
                        target = available_output_path(output_dir, config['output_name'],
                                                       config['params']['source'])
                        try:
                            os.rename(generated, target)
                            break
                        except FileExistsError:
                            continue
            return result
        finally:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=2)


class BatchInferenceSession:
    """Own one disposable inference process for a single Batch operation."""

    def __init__(self, model_path):
        self.model_path = model_path
        self.process = None

    def start(self):
        if self.process is not None:
            raise RuntimeError('Batch inference session already started.')
        flags = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
        if sys.platform == 'darwin' and getattr(sys, 'frozen', False):
            worker_args = [sys.executable, '--stomataquant-worker', '--batch', self.model_path]
        else:
            worker_args = [sys.executable, '-B', str(Path(__file__).with_name('inference_worker.py')),
                           '--batch', self.model_path]
        self.process = subprocess.Popen(
            worker_args,
            stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            encoding='utf-8', creationflags=flags)

    def predict(self, config, canceled):
        check_cancelled(canceled)
        if config['model_path'] != self.model_path:
            self.close()
            raise ValueError('Batch model changed during inference.')
        process = self.process
        if process is None or process.poll() is not None:
            raise RuntimeError('Batch inference process is not running.')
        output_dir = config['output_dir']
        os.makedirs(output_dir, exist_ok=True)
        try:
            with tempfile.TemporaryDirectory(prefix='.prediction.', dir=output_dir) as temporary:
                config = dict(config)
                params = dict(config['params'])
                params['project'] = temporary
                params['name'] = 'prediction'
                config['params'] = params
                request = Path(temporary) / 'request.json'
                response = Path(temporary) / 'response.json'
                request.write_text(json.dumps(config), encoding='utf-8')
                process.stdin.write(json.dumps({'request': str(request), 'response': str(response)}) + '\n')
                process.stdin.flush()
                while not response.exists():
                    if canceled():
                        # Windows cannot remove open prediction files before the child exits.
                        self.close()
                        raise OperationCancelled('Prediction canceled')
                    if process.poll() is not None:
                        raise RuntimeError(f'Batch inference process exited with status {process.returncode}.')
                    time.sleep(.05)
                check_cancelled(canceled)
                result = json.loads(response.read_text(encoding='utf-8'))
                if result.get('error'):
                    raise RuntimeError(result['error'])
                generated = Path(temporary) / 'prediction'
                if generated.exists():
                    while True:
                        target = available_output_path(output_dir, config['output_name'],
                                                       config['params']['source'])
                        try:
                            os.rename(generated, target)
                            break
                        except FileExistsError:
                            continue
                return result
        except BaseException:
            self.close()
            raise

    def close(self):
        process = self.process
        self.process = None
        if process is None:
            return
        if process.poll() is None:
            try:
                process.terminate()
            except OSError:
                if process.poll() is None:
                    raise
            try:
                process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=2)
        if process.stdin is not None:
            try:
                process.stdin.close()
            except OSError:
                pass


class CancellableThread(QThread):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._is_interrupted = False

    def requestInterruption(self):
        self._is_interrupted = True
        super().requestInterruption()

    def canceled(self):
        return self._is_interrupted or self.isInterruptionRequested()

    def check_interruption(self):
        check_cancelled(self.canceled)

from canvas import process_polygon_data
###-------------定义 ABorAD 推断线程-------------------
class ABorADInferenceThread(CancellableThread):
    inferenceFinished = pyqtSignal(float, float, str, object)  # 传递AB概率、AD概率、文件路径和错误信息

    def __init__(self, model_path, file_path, parent=None):
        super().__init__(parent)
        self.model_path = model_path
        self.file_path = file_path
        self.model = None

    def run(self):
        try:
            self.check_interruption()
            result = run_model_subprocess(dict(kind='classification', model_path=self.model_path,
                                               file_path=self.file_path), self.canceled)
            ab_probability, ad_probability = result['probabilities']
            
            # 发出信号，传递结果
            self.inferenceFinished.emit(ab_probability, ad_probability, self.file_path, None)
        
        except Exception as e:
            import traceback
            print(f"Error in ABorADInferenceThread: {str(e)}")
            print(traceback.format_exc())
            self.inferenceFinished.emit(0, 0, self.file_path, str(e))
        finally:
            # 释放资源
            self.model = None
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
            gc.collect()


###-------------定义 YOLO 分割推断线程-------------------
class YOLOSegInferenceThread(CancellableThread):
    inferenceFinished = pyqtSignal(object, str, object) # 定义推断完成信号
    # 该信号将传递推断结果(obj)、文件路径(str)和错误信息(obj)

    def __init__(self, model, file_path, inference_settings, parent=None, batch_session=None):
        super().__init__(parent) 
        self.model = model
        self.file_path = file_path
        self.inference_settings = dict(inference_settings)
        self.batch_session = batch_session
        self._is_interrupted = False  # 添加中断标志

    def requestInterruption(self):
        """请求中断线程执行"""
        super().requestInterruption()

    def run(self):
        try:
            self.check_interruption()
            # 获取推断设置
            conf = self.inference_settings.get("conf", 0.5)
            iou = self.inference_settings.get("iou", 0.7)
            device = self.inference_settings.get("device", "cpu").lower()
            if device == "gpu":
                device = "0"  # 或者根据实际情况设置 GPU 设备编号
            save_path = self.inference_settings.get(
                "save_path", macos_output_dir("Inference_OutPut") if sys.platform == "darwin"
                else os.path.join(os.getcwd(), "Inference_OutPut"))
            
            # 获取新增的参数
            imgsz = self.inference_settings.get("imgsz", 1024)
            max_det = self.inference_settings.get("max_det", 500)

            # 确保保存路径存在
            if not os.path.exists(save_path):
                os.makedirs(save_path)

            file_name = os.path.basename(self.file_path)

            # 收集所有要传递给 predict 方法的参数
            predict_params = {
                "source": self.file_path,
                "conf": conf,
                "iou": iou,
                "save": True,
                "save_txt": True,
                "device": device,
                "imgsz": imgsz,
                "max_det": max_det,
                "project": save_path,
                "show_conf": False,
                "show_boxes": False,
                "retina_masks": True,
                "name": file_name + "__" + source_suffix(self.file_path) + " generated by StomataQuant",
            }

            # 在调用 predict 方法之前，打印出所有参数
            print("The following parameters will be passed to self.model.predict when it is about to be called:：")
            for key, value in predict_params.items():
                print(f"{key}: {value}")


            # 调用 YOLO 的 predict 方法，传入参数字典
            while not _PREDICTION_LOCK.acquire(timeout=.05):
                self.check_interruption()
            try:
                self.check_interruption()
                model_path = getattr(self.model, '_stomataquant_source_path', None)
                if not model_path:
                    raise ValueError('The model source path is unavailable. Please reload the model.')
                config = dict(kind='segmentation', model_path=model_path,
                    params=predict_params, output_dir=save_path,
                    output_name=predict_params['name'])
                response = (self.batch_session.predict(config, self.canceled)
                            if self.batch_session is not None else
                            run_model_subprocess(config, self.canceled))
                results = [SerializedPrediction(item['path'], item['json'])
                           for item in response['predictions']]
            finally:
                _PREDICTION_LOCK.release()
            self.check_interruption()

            self.inferenceFinished.emit(results, self.file_path, None)
        

        except Exception as e:
            import traceback
            print(f"Error in YOLOSegInferenceThread: {str(e)}")
            print(traceback.format_exc())
            self.inferenceFinished.emit(None, self.file_path, e)
        finally:
            # 确保在推断完成后正确释放资源
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
            gc.collect()



class PolygonProcessThread(CancellableThread):
    processingFinished = pyqtSignal(object, list, object)  # 传递处理后的多边形字典、原始形状列表、错误信息

    def __init__(self, polygons_by_class, image_width, image_height, json_obj, parent=None):
        super().__init__(parent)
        self.polygons_by_class = polygons_by_class
        self.image_width = image_width
        self.image_height = image_height
        self.json_obj = json_obj
        self._is_interrupted = False

    def requestInterruption(self):
        """请求中断线程执行"""
        super().requestInterruption()

    def run(self):
        try:
            self.check_interruption()
            # 执行多边形处理
            processed_polygons = process_polygon_data(self.polygons_by_class, 
                                                     self.image_width, 
                                                     self.image_height, cancel_check=self.canceled)
            self.check_interruption()
            
            # 发出信号，传递处理结果
            self.processingFinished.emit(processed_polygons, self.json_obj, None)
        
        except Exception as e:
            import traceback
            print(f"Error in PolygonProcessThread: {str(e)}")
            print(traceback.format_exc())
            self.processingFinished.emit({}, self.json_obj, e)


###-------------定义热图生成线程-------------------
# 修改 HeatMapGenerationThread 类

class HeatMapGenerationThread(CancellableThread):
    heatmapGenerated = pyqtSignal(str, object)  # 传递保存路径和错误信息
    
    def __init__(self, original_image, shapes, feature_name, colormap_name, output_path, original_file_name="", scale_info=None, parent=None):
        super().__init__(parent)
        self.original_image = original_image.copy()
        self.shapes = [SimpleNamespace(shape_type=s.shape_type,
                      pointslist=[QPointF(p) for p in s.pointslist],
                      feature_results=copy.deepcopy(s.feature_results)) for s in shapes]
        self.feature_name = feature_name  # 特征名称
        self.colormap_name = colormap_name  # 颜色映射名称
        self.output_path = output_path  # 输出路径
        self.original_file_name = original_file_name  # 添加原始文件名参数
        self.scale_info = dict(scale_info) if scale_info else None
        self._is_interrupted = False  # 添加中断标志
    
    def requestInterruption(self):
        """请求中断线程执行"""
        super().requestInterruption()

    def run(self):
        while not _HEATMAP_LOCK.acquire(timeout=.05):
            if self.canceled():
                self.heatmapGenerated.emit('', OperationCancelled('Operation canceled'))
                return
        try:
            self._generate()
        finally:
            _HEATMAP_LOCK.release()

    def _generate(self):
        temp_colorbar = None
        try:
            self.check_interruption()
            # 导入必要的库
            import matplotlib
            matplotlib.use('Agg')  # 使用非交互式后端
            import matplotlib.pyplot as plt
            from matplotlib.colors import Normalize
            import numpy as np
            import tempfile
            import os
            from PyQt5.QtGui import QImage, QPainter, QPolygonF, QPen, QBrush, QColor, QPixmap
            from PyQt5.QtCore import Qt, QDateTime
            
            # 创建临时文件用于颜色条
            fd, temp_colorbar = tempfile.mkstemp(suffix='.png')
            os.close(fd)
            
            # 确保输出目录存在
            if not os.path.exists(self.output_path):
                os.makedirs(self.output_path)
            
            # 创建透明图层用于热图
            heatmap_image = QImage(self.original_image.size(), QImage.Format_ARGB32)
            heatmap_image.fill(Qt.transparent)
            
            # 提取特征值
            feature_values = []
            
            # 检查是否需要应用比例尺
            area_features = {'Area', 'ACH'}
            length_features = {'Perimeter', 'MER Length', 'MER Width', 'PCH'}
            needs_scale = self.feature_name in area_features | length_features
            unit_text = "pixel"
            
            if needs_scale and self.scale_info:
                unit_text = self.scale_info.get('unit', 'pixel')
            
            for shape in self.shapes:
                if (hasattr(shape, 'feature_results') and 
                    isinstance(shape.feature_results, dict) and 
                    self.feature_name in shape.feature_results):
                    value = shape.feature_results[self.feature_name]
                    if finite_numeric(value):
                        feature_values.append(value)
            
            if not feature_values:
                self.heatmapGenerated.emit("", f"没有找到特征: {self.feature_name}")
                return
            
            self.check_interruption()
            # 标准化特征值 (0 到 1)
            min_value = min(feature_values)
            max_value = max(feature_values)
            if min_value == max_value:
                margin = max(abs(float(min_value)) * .1, .5)
                min_value, max_value = min_value-margin, max_value+margin
            norm = Normalize(min_value, max_value)
            
            # 获取颜色映射
            cmap = plt.get_cmap(self.colormap_name)
            
            # 创建热图绘制器
            # Colorbar may expand a numerically singular range. Finalize the
            # shared Normalize before painting any Shape, including near constants.
            self.check_interruption()
            # 创建颜色条
            plt.close('all')  # 确保关闭之前的图形
            fig, ax = plt.subplots(figsize=(6, 0.6))
            fig.subplots_adjust(bottom=0.5)
            cb = plt.colorbar(plt.cm.ScalarMappable(norm=norm, cmap=cmap), 
                            cax=ax, orientation='horizontal')
            
            # 为颜色条添加适当的单位
            if needs_scale:
                # 为不同特征类型添加适当的单位标签
                if self.feature_name in area_features:
                    cb.set_label(f'{self.feature_name} ({unit_text}²)')
                elif self.feature_name in length_features:
                    cb.set_label(f'{self.feature_name} ({unit_text})')
            else:
                cb.set_label(f'{self.feature_name}')
                
            fig.savefig(temp_colorbar, bbox_inches='tight', dpi=100)
            plt.close(fig)

            painter = QPainter()
            painter.begin(heatmap_image)
            painter.setRenderHint(QPainter.Antialiasing)
                        
            # 在for循环中的计算颜色部分
            for shape in self.shapes:
                if (not hasattr(shape, 'feature_results') or 
                    not isinstance(shape.feature_results, dict) or 
                    self.feature_name not in shape.feature_results):
                    continue
                
                value = shape.feature_results[self.feature_name]
                if not finite_numeric(value):
                    continue
                
                # 计算颜色 - 修改这部分代码
                rgba = cmap(norm(value))
                color = QColor(
                    int(rgba[0] * 255), 
                    int(rgba[1] * 255), 
                    int(rgba[2] * 255), 
                    180  # Alpha透明度
                )
                
                # 绘制多边形
                if shape.shape_type == 'polygon' and len(shape.pointslist) > 2:
                    polygon = QPolygonF(shape.pointslist)
                    painter.setPen(QPen(color, 2))
                    painter.setBrush(QBrush(color))
                    painter.drawPolygon(polygon)
            
            painter.end()
            
            # 创建结果图像
            result_image = QImage(self.original_image.size(), QImage.Format_RGB32)
            result_painter = QPainter()
            result_painter.begin(result_image)
            result_painter.drawImage(0, 0, self.original_image)
            result_painter.drawImage(0, 0, heatmap_image)
            result_painter.end()
            

            
            # 加载颜色条图像
            colorbar_image = QImage(temp_colorbar)
            
            # 创建最终图像
            final_height = result_image.height() + colorbar_image.height() + 10
            final_image = QImage(result_image.width(), final_height, QImage.Format_RGB32)
            final_image.fill(QColor(255, 255, 255))
            
            # 绘制到最终图像
            final_painter = QPainter()
            final_painter.begin(final_image)
            final_painter.drawImage(0, 0, result_image)
            
            # 在底部绘制颜色条
            scaled_colorbar = colorbar_image.scaled(
                result_image.width() - 20, 
                colorbar_image.height(),
                Qt.KeepAspectRatio, 
                Qt.SmoothTransformation
            )
            final_painter.drawImage(
                (final_image.width() - scaled_colorbar.width()) // 2,
                result_image.height() + 5, 
                scaled_colorbar
            )
            final_painter.end()
            
            # 保存结果
            # 保存结果
            # 保存结果
            # 保存结果
            if self.original_file_name:
                # 提取文件名（不包含路径和扩展名）
                base_name = os.path.basename(self.original_file_name)
                file_name_without_ext = os.path.splitext(base_name)[0]
                file_name = f"{self.feature_name}_{file_name_without_ext}.png"
            else:
                # 如果没有原始文件名，使用时间戳作为后备方案
                file_name = f"{self.feature_name}_{QDateTime.currentDateTime().toString('yyyyMMdd_hhmmss')}.png"
            
            # 构建完整的文件保存路径
            # Publish only a complete PNG, and never replace another image's result.
            self.check_interruption()
            fd, temporary_png = tempfile.mkstemp(prefix='.heatmap.', suffix='.png', dir=self.output_path)
            os.close(fd)
            try:
                if not final_image.save(temporary_png, 'PNG'):
                    raise OSError('Failed to save heatmap image.')
                while True:
                    file_path = available_output_path(self.output_path, file_name,
                                                      self.original_file_name or file_name)
                    try:
                        if os.name == 'nt':
                            os.rename(temporary_png, file_path)
                        else:
                            os.link(temporary_png, file_path)
                        break
                    except FileExistsError:
                        continue
                self.heatmapGenerated.emit(str(file_path), None)
            finally:
                if os.path.exists(temporary_png):
                    os.unlink(temporary_png)

                
            # 清理临时文件
            try:
                if os.path.exists(temp_colorbar):
                    os.remove(temp_colorbar)
            except:
                pass
                
        except Exception as e:
            import traceback
            print(f"Error generating Heat Map: {str(e)}")
            print(traceback.format_exc())
            self.heatmapGenerated.emit("", e)
        finally:
            if temp_colorbar and os.path.exists(temp_colorbar):
                os.remove(temp_colorbar)
