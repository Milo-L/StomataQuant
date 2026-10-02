from shape_spatial import Grid, ShapeList
from shape_history import History, shape_identity
import display_settings as display
# canvas.py
from PIL.FtexImagePlugin import Format
from PyQt5 import QtCore, QtGui, QtWidgets
from PyQt5.QtCore import QPointF, QLineF
from PyQt5.QtGui import QColor
from matplotlib import scale
from shape import Shape
from shapely.geometry import Polygon, MultiPolygon
from shapely.ops import unary_union
from shapely.strtree import STRtree
import numpy as np
import copy
try:
    import numba
except ImportError:
    numba = None
from geometry import (repair_polygon, ProcessedPolygons, minimum_rectangle_size,
                      rectangle_side_lengths, MIN_POLYGON_VERTICES, require_valid_polygon,
                      polygon_moments)
from task_support import check_cancelled



USE_NUMBA = numba is not None  # Acceleration is optional


def check_numba():
    """检查 Numba 是否可用，如果出现错误则禁用"""
    if numba is None:
        return False
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
# 全局函数，关于推理后多边形的后处理
# Global function, post-processing for the resulting polygons after reasoning
######################################################################

def process_polygon_data(class_polygons_dict, image_width=None, image_height=None, cancel_check=None):
    """
    完整处理多边形数据，包括移除内部点、处理离群点，并确保多边形有效性
    返回:
    处理后的多边形字典
    """
    # 首先处理内部点重叠
    processed_dict = optimized_process_raw_polygons(class_polygons_dict, cancel_check=cancel_check)
    # 然后处理离群点，传入图像尺寸
    check_cancelled(cancel_check)
    cleaned_dict = remove_outlier_points(processed_dict, image_width=image_width, image_height=image_height)
    # 最后确保所有多边形都是有效的
    check_cancelled(cancel_check)
    final_dict = validate_and_fix_polygons(cleaned_dict)
    overlap_audit = {(r['classnum'], r['index']): r for r in processed_dict.audit}
    for record in final_dict.audit:
        xs, ys = class_polygons_dict[record['classnum']][record['index']]
        record['source_x'], record['source_y'] = list(xs), list(ys)
        prior = overlap_audit[record['classnum'], record['index']]
        if prior['status'] != 'unchanged' and record['status'] != 'rejected':
            record.update({k: v for k, v in prior.items()
                           if k in ('status', 'reason', 'proposed_area_after')})
        if record['status'] == 'rejected':
            final_dict[record['classnum']][record['index']] = None
            continue
        if len(xs) >= 3 and len(xs) == len(ys) and np.isfinite(list(zip(xs, ys))).all():
            source = Polygon(zip(xs, ys))
            source_area = source.area
            record['source_area'] = record['area_before'] = source_area
            after = record['area_after']
            change = ((after-source_area)/source_area if source_area and after is not None else None)
            record['total_area_change'] = change
            record['relative_area_change'] = abs(change) if change is not None else None
            output = final_dict[record['classnum']][record['index']]
            if source.is_valid and not source.equals(Polygon(zip(*output))):
                if change is not None and abs(change) > .01:
                    record.update(status='modified', reason='Total contour area change exceeds 1%')
                elif record['status'] == 'unchanged':
                    record.update(status='repaired', reason='Contour geometry changed during post-processing')
        output = final_dict[record['classnum']][record['index']]
        try:
            x_values, y_values = output
            points = [QPointF(x, y) for x, y in zip(x_values, y_values)]
            if len(x_values) != len(y_values) or len({(p.x(), p.y()) for p in points}) < MIN_POLYGON_VERTICES:
                raise ValueError(f'Polygon requires at least {MIN_POLYGON_VERTICES} distinct vertices.')
            require_valid_polygon(points)
            polygon_moments(points)
            if image_width and image_height:
                # Validate the exact six-decimal geometry that Save -> Import will use.
                from annotation_io import parse_annotation_line
                line = '0 ' + ' '.join(f'{value:.6f}' for p in points
                                      for value in (p.x()/image_width, p.y()/image_height))
                parse_annotation_line(line, 'polygon', image_width, image_height)
            record['processed_x'], record['processed_y'] = list(x_values), list(y_values)
        except Exception as error:
            record.update(status='rejected', reason=str(error))
            final_dict[record['classnum']][record['index']] = None
    print('processing polygon data is finished')
    return final_dict

def _robust_point_in_polygon_python(point_x, point_y, vertices_x, vertices_y, tolerance=1e-9):
    """更稳健的点在多边形内测试，处理边界情况"""
    n = len(vertices_x)
    inside = False
    on_edge = False
    j = n - 1

    for i in range(n):
        # 检查点是否在多边形顶点上
        if abs(vertices_x[i] - point_x) < tolerance and abs(vertices_y[i] - point_y) < tolerance:
            return True, False  # 在顶点上

        # 检查点是否在多边形边上
        if (((vertices_y[i] <= point_y and point_y < vertices_y[j]) or
            (vertices_y[j] <= point_y and point_y < vertices_y[i])) and
            (point_x < (vertices_x[j] - vertices_x[i]) * (point_y - vertices_y[i]) / 
            (vertices_y[j] - vertices_y[i]) + vertices_x[i])):
            inside = not inside

        # 检查点是否在边上
        if (min(vertices_x[i], vertices_x[j]) <= point_x <= max(vertices_x[i], vertices_x[j]) and
            min(vertices_y[i], vertices_y[j]) <= point_y <= max(vertices_y[i], vertices_y[j])):
            # 计算点到线段的距离
            if abs(vertices_y[j] - vertices_y[i]) < tolerance:  # 水平线
                if abs(point_y - vertices_y[i]) < tolerance:
                    on_edge = True
            elif abs(vertices_x[j] - vertices_x[i]) < tolerance:  # 垂直线
                if abs(point_x - vertices_x[i]) < tolerance:
                    on_edge = True
            else:  # 一般线段
                # 计算点到线的距离
                dist = abs((vertices_y[j] - vertices_y[i]) * point_x - 
                            (vertices_x[j] - vertices_x[i]) * point_y + 
                            vertices_x[j] * vertices_y[i] - vertices_y[j] * vertices_x[i]) / \
                    np.sqrt((vertices_y[j] - vertices_y[i])**2 + (vertices_x[j] - vertices_x[i])**2)
                if dist < tolerance:
                    on_edge = True

        j = i

    return inside, on_edge


def optimized_process_raw_polygons(class_polygons_dict, cancel_check=None):
    """Subtract actual overlap, preserving every non-overlapping region.

    Earlier contours own overlapping area. Shapes with holes, multiple components
    or no remaining area cannot be represented by a single editable contour;
    retain a valid original contour and record the overlap in the audit.
    """
    result = ProcessedPolygons()
    for classnum, polygons in class_polygons_dict.items():
        result[classnum] = []
        # Index the original valid contours once. Ownership is still determined
        # by input order; only earlier contours whose bounds intersect can
        # subtract area from the current one.
        indexed = []
        positions = []
        by_position = {}
        for index, (xs, ys) in enumerate(polygons):
            if index % 256 == 0:
                check_cancelled(cancel_check)
            if len(xs) >= 3 and len(xs) == len(ys) and np.isfinite(list(zip(xs, ys))).all():
                polygon = Polygon(zip(xs, ys))
                if polygon.is_valid and polygon.area > 0:
                    indexed.append(polygon)
                    positions.append(index)
                    by_position[index] = polygon
        tree = STRtree(indexed) if indexed else None
        for index, (xs, ys) in enumerate(polygons):
            check_cancelled(cancel_check)
            original = (list(xs), list(ys))
            output = original
            record = {'classnum': classnum, 'index': index, 'status': 'unchanged'}
            polygon = by_position.get(index)
            if polygon is not None:
                    record['area_before'] = polygon.area
                    candidates = sorted(int(i) for i in tree.query(polygon, predicate='intersects')
                                        if positions[int(i)] < index)
                    if candidates:
                        occupied = indexed[candidates[0]]
                        for candidate in candidates[1:]:
                            occupied = occupied.union(indexed[candidate])
                        difference = polygon.difference(occupied)
                    else:
                        difference = polygon
                    if not difference.equals(polygon):
                        record['proposed_area_after'] = difference.area
                        if (difference.geom_type == 'Polygon' and not difference.is_empty
                                and not difference.interiors and difference.area > 0):
                            coordinates = list(difference.exterior.coords)[:-1]
                            output = ([p[0] for p in coordinates], [p[1] for p in coordinates])
                            change = abs(difference.area-polygon.area)/polygon.area
                            record.update(status='modified' if change > .01 else 'repaired',
                                          reason='Overlap removed by polygon difference')
                        else:
                            record.update(status='overlap_retained',
                                          reason='Overlap subtraction requires multiple contours or holes; original retained')
                    record['area_after'] = Polygon(zip(*output)).area
                    record['relative_area_change'] = abs(record['area_after']-polygon.area)/polygon.area
            result[classnum].append(output)
            result.audit.append(record)
    return result

def remove_outlier_points(class_polygons_dict, angle_threshold=15, dist_factor=2.0, image_width=None,
                          image_height=None):
    """
    从多边形中移除离群点

    参数:
    class_polygons_dict: 字典，键为classnum，值为该类的多边形点列表
    angle_threshold: 角度阈值(度)，小于此角度的顶点可能是离群点
    dist_factor: 距离因子，用于判断点是否离群
    image_width: 图像宽度，可选
    image_height: 图像高度，可选

    返回:
    处理后的多边形字典
    """
    result_dict = {}

    for classnum, polygons in class_polygons_dict.items():
        result_dict[classnum] = []

        for points_x, points_y in polygons:
            # 如果点数太少，无需处理
            if len(points_x) <= 20:
                result_dict[classnum].append((points_x, points_y))
                continue

            # 转换为QPointF列表以便计算
            points = [QPointF(x, y) for x, y in zip(points_x, points_y)]

            # 如果自动检测判断不需要处理离群点，则跳过
            # 这里传入图像尺寸参数
            if not need_outlier_removal(points, image_width, image_height):
                result_dict[classnum].append((points_x, points_y))
                continue

            # 处理离群点
            filtered_points = filter_outlier_points(points, angle_threshold, dist_factor)

            # 提取处理后的x和y坐标
            filtered_x = [p.x() for p in filtered_points]
            filtered_y = [p.y() for p in filtered_points]

            # 添加到结果
            result_dict[classnum].append((filtered_x, filtered_y))

    return result_dict

def need_outlier_removal(points, image_width=None, image_height=None, boundary_tolerance=5):
    """自动判断多边形是否需要离群点移除"""
    global USE_NUMBA

    # 计算多边形特征
    n = len(points)
    if n <= 20:
        return False

    # 检查是否是边界多边形
    if image_width is not None and image_height is not None:
        # 检查是否有任何点在图像边界附近
        for point in points:
            x, y = point.x(), point.y()
            if (x <= boundary_tolerance or x >= image_width - boundary_tolerance or
                    y <= boundary_tolerance or y >= image_height - boundary_tolerance):
                # 多边形有点在边界上，不需要离群点移除
                return False

    # 提取顶点坐标为NumPy数组
    vertices_x = np.array([p.x() for p in points])
    vertices_y = np.array([p.y() for p in points])

    if USE_NUMBA:
        try:
            # 使用Numba加速计算边长统计信息
            mean_length, std_length, _ = _calculate_edges_stats_numba(vertices_x, vertices_y)

            # 如果边长变化太大，可能有离群点
            if std_length / mean_length > 0.8:
                return True

            # 计算锐角数量
            sharp_angles_count = _count_sharp_angles_numba(vertices_x, vertices_y, np.radians(30))

            # 如果锐角比例超过阈值，可能有离群点
            if sharp_angles_count / n > 0.1:
                return True

            return False
        except Exception as e:
            print(f"Numba acceleration failed in need_outlier_removal: {e}")
            USE_NUMBA = False

    # 降级到原始实现
    # 1. 计算边长标准差
    edges_length = []
    for i in range(n):
        p1 = points[i]
        p2 = points[(i + 1) % n]
        length = _calculate_distance_numba(p1.x(), p1.y(), p2.x(), p2.y())
        edges_length.append(length)

    mean_length = sum(edges_length) / len(edges_length)
    std_length = np.sqrt(sum((x - mean_length) ** 2 for x in edges_length) / len(edges_length))

    # 如果边长变化太大，可能有离群点
    if std_length / mean_length > 0.8:
        return True

    # 2. 检查锐角
    sharp_angles_count = 0
    for i in range(n):
        p1 = points[(i - 1) % n]
        p2 = points[i]
        p3 = points[(i + 1) % n]

        # 计算角度(弧度)
        angle = calculate_angle(p1, p2, p3)

        # 检查是否是锐角(小于30度)
        if angle < np.radians(30):
            sharp_angles_count += 1

    # 如果锐角比例超过阈值，可能有离群点
    if sharp_angles_count / n > 0.1:
        return True

    return False

def filter_outlier_points(points, angle_threshold=15, dist_factor=2.0):
    """使用角度和距离方法过滤离群点，采用更稳健的策略"""
    global USE_NUMBA

    n = len(points)
    if n <= 20:
        return points

    # 提取顶点坐标为NumPy数组
    vertices_x = np.array([p.x() for p in points])
    vertices_y = np.array([p.y() for p in points])

    if USE_NUMBA:
        try:
            # 计算边长
            _, _, edge_lengths = _calculate_edges_stats_numba(vertices_x, vertices_y)
            median_length = np.median(edge_lengths)

            # 使用Numba加速计算离群评分
            outlier_scores = _calculate_outlier_scores_numba(
                vertices_x, vertices_y, angle_threshold, dist_factor, median_length)

            # 处理评分结果
            threshold_score = 70  # 最低评分阈值
            is_outlier = np.zeros(n, dtype=bool)

            # 找出高于阈值的点
            candidates = []
            for i in range(n):
                if outlier_scores[i] > threshold_score:
                    candidates.append((i, outlier_scores[i]))

            # 按评分从高到低排序
            candidates.sort(key=lambda x: x[1], reverse=True)

            # 确定要删除的点数量
            if n > 50:
                max_outliers = max(0, n // 50)
            else:
                max_outliers = max(0, n // 100)

            # 如果待删除点过多，只取评分最高的几个
            if len(candidates) > max_outliers:
                candidates = candidates[:max_outliers]

            # 设置标记
            for i, _ in candidates:
                is_outlier[i] = True

            # 构建结果
            filtered_points = [points[i] for i in range(n) if not is_outlier[i]]

            # 确保至少有3个点，否则返回原始点集
            if len(filtered_points) < 3:
                return points

            return filtered_points
        except Exception as e:
            print(f"Numba acceleration failed in filter_outlier_points: {e}")
            USE_NUMBA = False

    # 降级到原始实现
    # 保持原有实现不变
    # 初始化标记和评分
    is_outlier = [False] * n
    outlier_score = [0] * n  # 离群点评分，越高越可能是离群点

    # 计算相邻边长的中位数
    edge_lengths = []
    for i in range(n):
        p1 = points[i]
        p2 = points[(i + 1) % n]
        length = _calculate_distance_numba(p1.x(), p1.y(), p2.x(), p2.y())
        edge_lengths.append(length)

    median_length = np.median(edge_lengths)

    # 同时使用角度和距离评估每个点
    for i in range(n):
        p1 = points[(i - 1) % n]
        p2 = points[i]
        p3 = points[(i + 1) % n]

        # 计算角度(弧度)
        angle = calculate_angle(p1, p2, p3)
        angle_degree = np.degrees(angle)

        # 计算与相邻点的距离
        dist1 = _calculate_distance_numba(p1.x(), p1.y(), p2.x(), p2.y())
        dist2 = _calculate_distance_numba(p2.x(), p2.y(), p3.x(), p3.y())

        # 角度评分 (0-100)
        if angle_degree < angle_threshold:
            angle_score = 100 * (1 - angle_degree / angle_threshold)
        else:
            angle_score = 0

        # 距离评分 (0-100)
        dist_ratio1 = dist1 / median_length if median_length > 0 else 0
        dist_ratio2 = dist2 / median_length if median_length > 0 else 0

        if dist_ratio1 > dist_factor and dist_ratio2 > dist_factor:
            dist_score = 100 * min(1, (min(dist_ratio1, dist_ratio2) - dist_factor) / dist_factor)
        else:
            dist_score = 0

        # 综合评分 - 只有当两种方法都认为是离群点时才给高分
        if angle_score > 0 and dist_score > 0:
            outlier_score[i] = (angle_score + dist_score) / 2
        elif angle_score > 75:  # 角度非常小的情况下单独判断
            outlier_score[i] = angle_score * 0.8
        elif dist_score > 75:  # 距离非常大的情况下单独判断
            outlier_score[i] = dist_score * 0.8
        else:
            outlier_score[i] = 0

    candidates = [(i, score) for i, score in enumerate(outlier_score) if score > 70]
    candidates.sort(key=lambda item: item[1], reverse=True)
    max_outliers = n // 50 if n > 50 else n // 100
    removed = {i for i, _ in candidates[:max_outliers]}
    filtered_points = [point for i, point in enumerate(points) if i not in removed]
    return filtered_points if len(filtered_points) >= 3 else points


def validate_and_fix_polygons(class_polygons_dict):
    result = ProcessedPolygons()
    for classnum, polygons in class_polygons_dict.items():
        result[classnum] = []
        for index, (xs, ys) in enumerate(polygons):
            repaired, record = repair_polygon(xs, ys)
            result[classnum].append(repaired)
            record.update(classnum=classnum, index=index)
            result.audit.append(record)
    return result


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

def calculate_angle(p1, p2, p3):
    """计算三点形成的角度(弧度)"""
    global USE_NUMBA

    v1x = p1.x() - p2.x()
    v1y = p1.y() - p2.y()
    v2x = p3.x() - p2.x()
    v2y = p3.y() - p2.y()

    if USE_NUMBA:
        try:
            return _calculate_angle_numba_accelerated(v1x, v1y, v2x, v2y)
        except Exception as e:
            print(f"Numba acceleration failed in calculate_angle: {e}")
            USE_NUMBA = False

    # 向量夹角计算
    dot_product = v1x * v2x + v1y * v2y
    len1 = np.sqrt(v1x ** 2 + v1y ** 2)
    len2 = np.sqrt(v2x ** 2 + v2y ** 2)

    # 防止除零错误
    if len1 < 1e-6 or len2 < 1e-6:
        return 0

    cos_angle = dot_product / (len1 * len2)
    # 限制在[-1, 1]范围内
    cos_angle = max(-1, min(1, cos_angle))

    return np.arccos(cos_angle)

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

        # 新增加速函数
        @numba.jit(nopython=True, cache=True)
        def _calculate_angle_numba_accelerated(v1x, v1y, v2x, v2y):
            """计算两个向量之间的角度(弧度)"""
            dot_product = v1x * v2x + v1y * v2y
            len1 = np.sqrt(v1x ** 2 + v1y ** 2)
            len2 = np.sqrt(v2x ** 2 + v2y ** 2)

            if len1 < 1e-6 or len2 < 1e-6:
                return 0

            cos_angle = dot_product / (len1 * len2)
            cos_angle = max(-1, min(1, cos_angle))

            return np.arccos(cos_angle)

        @numba.jit(nopython=True, cache=True)
        def _calculate_edges_stats_numba(vertices_x, vertices_y):
            """计算多边形边长的统计信息"""
            n = len(vertices_x)
            edges_length = np.zeros(n)

            for i in range(n):
                j = (i + 1) % n
                dx = vertices_x[j] - vertices_x[i]
                dy = vertices_y[j] - vertices_y[i]
                edges_length[i] = np.sqrt(dx * dx + dy * dy)

            mean_length = np.mean(edges_length)
            std_length = np.std(edges_length)

            return mean_length, std_length, edges_length

        @numba.jit(nopython=True, cache=True)
        def _count_sharp_angles_numba(vertices_x, vertices_y, threshold_radians):
            """统计多边形中小于给定阈值的锐角数量"""
            n = len(vertices_x)
            sharp_angles_count = 0

            for i in range(n):
                prev_idx = (i - 1) % n
                next_idx = (i + 1) % n

                v1x = vertices_x[prev_idx] - vertices_x[i]
                v1y = vertices_y[prev_idx] - vertices_y[i]
                v2x = vertices_x[next_idx] - vertices_x[i]
                v2y = vertices_y[next_idx] - vertices_y[i]

                angle = _calculate_angle_numba_accelerated(v1x, v1y, v2x, v2y)

                if angle < threshold_radians:
                    sharp_angles_count += 1

            return sharp_angles_count

        @numba.jit(nopython=True, cache=True)
        def _calculate_outlier_scores_numba(vertices_x, vertices_y, angle_threshold, dist_factor, median_length):
            """计算每个点的离群评分"""
            n = len(vertices_x)
            outlier_scores = np.zeros(n)

            for i in range(n):
                prev_idx = (i - 1) % n
                next_idx = (i + 1) % n

                # 计算向量
                v1x = vertices_x[prev_idx] - vertices_x[i]
                v1y = vertices_y[prev_idx] - vertices_y[i]
                v2x = vertices_x[next_idx] - vertices_x[i]
                v2y = vertices_y[next_idx] - vertices_y[i]

                # 计算角度
                angle = _calculate_angle_numba_accelerated(v1x, v1y, v2x, v2y)
                angle_degree = angle * 180.0 / np.pi

                # 计算与相邻点的距离
                dist1 = np.sqrt(
                    (vertices_x[i] - vertices_x[prev_idx]) ** 2 + (vertices_y[i] - vertices_y[prev_idx]) ** 2)
                dist2 = np.sqrt(
                    (vertices_x[i] - vertices_x[next_idx]) ** 2 + (vertices_y[i] - vertices_y[next_idx]) ** 2)

                # 角度评分 (0-100)
                angle_score = 0.0
                if angle_degree < angle_threshold:
                    angle_score = 100.0 * (1.0 - angle_degree / angle_threshold)

                # 距离评分 (0-100)
                dist_score = 0.0
                dist_ratio1 = dist1 / median_length if median_length > 0 else 0
                dist_ratio2 = dist2 / median_length if median_length > 0 else 0

                if dist_ratio1 > dist_factor and dist_ratio2 > dist_factor:
                    dist_score = 100.0 * min(1.0, (min(dist_ratio1, dist_ratio2) - dist_factor) / dist_factor)

                # 综合评分
                if angle_score > 0 and dist_score > 0:
                    outlier_scores[i] = (angle_score + dist_score) / 2.0
                elif angle_score > 75:
                    outlier_scores[i] = angle_score * 0.8
                elif dist_score > 75:
                    outlier_scores[i] = dist_score * 0.8

            return outlier_scores
        
        _robust_point_in_polygon = numba.jit(nopython=True, cache=True)(_robust_point_in_polygon_python)

        @numba.jit(nopython=True, cache=True)
        def _improved_remove_points_inside_other_polygon(polygon_points_x, polygon_points_y, 
                                                    other_polygon_points_x, other_polygon_points_y):
            """
            改进的重叠点检测，考虑边界情况
            """
            n_points = len(polygon_points_x)
            keep_mask = np.ones(n_points, dtype=np.bool_)
            
            for i in range(n_points):
                # 检查当前点是否在另一个多边形内部或边界上
                inside, on_edge = _robust_point_in_polygon(
                    polygon_points_x[i], polygon_points_y[i], 
                    other_polygon_points_x, other_polygon_points_y)
                
                if inside or on_edge:
                    keep_mask[i] = False
            
            return keep_mask
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
        self._spatial = Grid()
        self._shape_by_id = {}
        self._measurement_dirty = set()
        self._measurement_removed = set()
        self._measurement_scale_version = 0
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
        self._edit_before = None
        self._edit_original = ()
        self._history = History()
        self._history_generation = 0
        self._history_pending = None
        self._restoring_history = False
        self.shapesChanged.connect(self._commit_pending_history)
        self.undo_stack = [] # 维护一个操作栈，用于保存历史状态
        #self.current_cursor = QtCore.Qt.ArrowCursor  # 缓存当前光标状态
        self.setFlag(QtWidgets.QGraphicsItem.ItemUsesExtendedStyleOption, True)
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
    @property
    def shapes(self):
        return self._shapes

    @shapes.setter
    def shapes(self, value):
        old = list(getattr(self, '_shapes', ()))
        value = list(value)
        self.measurement_validate_members(value, old)
        if hasattr(self, '_shapes'):
            self._shapes.owner = lambda: None
        self._shapes = ShapeList(value, self._spatial, self)
        self.measurement_members_changed(self._shapes, old)
        self._shapes.changed(check_removed=True)

    def measurement_validate_members(self, added, removed=()):
        removed_ids = {shape_identity(s) for s in removed}
        seen = set()
        for shape in added:
            uid = shape_identity(shape)
            if uid in seen or (uid in self._shape_by_id and uid not in removed_ids):
                raise ValueError('A Shape identity may occur only once in a Canvas.')
            if any(owner is not self for owner in shape._measurement_owners):
                raise ValueError('A live Shape cannot belong to two Canvases; copy it first.')
            seen.add(uid)

    def measurement_changed(self, shape):
        uid = shape_identity(shape)
        if self._shape_by_id.get(uid) is shape:
            self._measurement_dirty.add(uid)

    def measurement_members_changed(self, added, removed):
        added = {shape_identity(s): s for s in added}
        for shape in removed:
            uid = shape_identity(shape)
            if added.get(uid) is shape:
                continue
            shape._measurement_owners.discard(self)
            shape._selected = False
            for name in ('hovered_shape', '_last_hover_shape', 'scaling_shape', 'rotating_shape', 'current_shape'):
                if getattr(self, name, None) is shape:
                    setattr(self, name, None)
                    if name == 'scaling_shape':
                        self.scaling_rotated_rectangle = False
                    elif name == 'rotating_shape':
                        self.rotating = False
            self._shape_by_id.pop(uid, None)
            self._measurement_dirty.discard(uid)
            self._measurement_removed.add(uid)
        for uid, shape in added.items():
            previous = self._shape_by_id.get(uid)
            if previous is not None and previous is not shape:
                raise ValueError('Duplicate Shape identity in one Canvas.')
            self._shape_by_id[uid] = shape
            shape._measurement_owners.add(self)
            self._measurement_removed.discard(uid)
            if previous is not shape:
                self._measurement_dirty.add(uid)
        if removed:
            if hasattr(self, 'selected_shape'):
                self.selected_shape = [s for s in self.selected_shape
                                       if self._shape_by_id.get(shape_identity(s)) is s]
            if getattr(self, '_edit_original', ()):
                self._edit_original = tuple((s, points) for s, points in self._edit_original
                                            if self._shape_by_id.get(shape_identity(s)) is s)

    def _spatial_candidates(self, rect, font=None, scale=None):
        if len(self.shapes) < 128:
            return self.shapes
        return self._spatial.query(self.shapes, rect,
                                   self.scale_factor if scale is None else scale, font)

    def bounded_point(self, point):
        return QPointF(min(max(point.x(),0.),self.image_size.width()),
                       min(max(point.y(),0.),self.image_size.height()))

    def _minimum_rectangle_size(self):
        return minimum_rectangle_size(self.image_size.width(), self.image_size.height())

    def _clamp_rectangle_corner(self, anchor, moving, previous=None):
        minimum = self._minimum_rectangle_size()
        def coordinate(start, target, old, limit):
            delta = target - start
            if delta == 0:
                direction = -1 if (old is not None and old < start) or (old is None and start >= limit) else 1
            else:
                direction = -1 if delta < 0 else 1
            return start + direction * max(abs(delta), minimum)
        return QPointF(coordinate(anchor.x(), moving.x(), previous.x() if previous else None,
                                  self.image_size.width()),
                       coordinate(anchor.y(), moving.y(), previous.y() if previous else None,
                                  self.image_size.height()))

    def _clamp_rotated_first_edge(self, anchor, moving):
        dx, dy = moving.x() - anchor.x(), moving.y() - anchor.y()
        length = np.hypot(dx, dy)
        minimum = self._minimum_rectangle_size()
        if length == 0:
            return QPointF(anchor.x() + minimum, anchor.y())
        factor = max(1.0, minimum / length)
        return QPointF(anchor.x() + dx * factor, anchor.y() + dy * factor)

    def _geometry_notice(self, message):
        scene = self.scene()
        views = scene.views() if scene is not None else []
        window = views[0].window() if views else None
        if window is not None and hasattr(window, 'statusBar'):
            window.statusBar().showMessage(message, 4000)

    def add_shape(self, shape):
        """添加形状到场景中,被duplicate_shape调用"""
        """Add shapes to the scene, which is called by duplicate_shape"""
        if not any(s is shape for s in self.shapes):
            self.shapes.append(shape)
            # 确保新添加的形状与画布使用相同的缩放因子
            if hasattr(shape, 'set_scale_factor'):
                shape.set_scale_factor(self.scale_factor)

            self.update(shape.visual_bounds())
            self.shapesChanged.emit()

    def remove_shape(self, shape):
        """从场景中安全地移除形状，清理所有引用"""
        "Remove shapes from the scene safely and clear all references."
        if any(s is shape for s in self.shapes):
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
            if shape is self.hovered_shape:
                self.hovered_shape = None

            self.selected_shape[:] = [s for s in self.selected_shape if s is not shape]
            # 清除其他引用
            if hasattr(self, 'scaling_shape') and self.scaling_shape is shape:
                self.scaling_shape = None
                self.scaling_rotated_rectangle = False

            if hasattr(self, 'rotating_shape') and self.rotating_shape is shape:
                self.rotating_shape = None
                self.rotating = False

            # 通知界面更新
            self.update(shape.visual_bounds())
            self.shapesChanged.emit()

    def boundingRect(self):
        width, height = self.image_size.width(), self.image_size.height()
        rect = QtCore.QRectF(0, 0, width, height)
        if display.current.auto_scale:
            # Boundary coordinates are exportable; their visible marker must also
            # receive mouse presses after viewport pixel rounding (including Fit).
            margin = max(12 / max(self.scale_factor, 1e-6),
                         display.point_radius(self.scale_factor, 4) + 4 / max(self.scale_factor, 1e-6))
            rect.adjust(-margin, -margin, margin, margin)
        else:
            # Reserve space for markers/strokes at the image edge, including AA.
            margin = max(12.0, display.current.point_diameter / 2 + 2,
                         display.current.line_width / 2 + 2) / max(self.scale_factor, 1e-6)
            # Rotation handles can extend beyond the image by 15% + 15 image pixels.
            # Bound that extent without scanning thousands of shapes on each query.
            margin += max(width, height) * .15 + 15
            rect.adjust(-margin, -margin, margin, margin)
        return rect

    def set_scale_factor(self, scale):
        if self.scale_factor == scale:
            return
        self.prepareGeometryChange()
        self.scale_factor = scale
        for shape in self.shapes:
            if hasattr(shape, 'set_scale_factor'):
                shape.set_scale_factor(scale)
        if self.current_shape:
            self.current_shape.set_scale_factor(scale)

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
    def _screen_tolerance(self, pixels):
        return pixels / max(self.scale_factor, 1e-6)

    def _edit_vertex(self, shape, pos, tolerance, inside=False):
        index = self.find_closest_vertex(pos, shape.pointslist, tolerance)
        if index >= 0 and inside:
            # Tiny shapes need a body target even when screen-sized handles overlap.
            if QLineF(pos, shape.get_center()).length() < QLineF(pos, shape.pointslist[index]).length():
                return -1
        return index

    @staticmethod
    def _segment_distance_squared(pos, a, b):
        dx, dy = b.x() - a.x(), b.y() - a.y()
        length_squared = dx * dx + dy * dy
        t = max(0., min(1., ((pos.x()-a.x())*dx + (pos.y()-a.y())*dy) / length_squared)) if length_squared else 0.
        return (pos.x()-a.x()-t*dx)**2 + (pos.y()-a.y()-t*dy)**2

    def _polygon_edge_target(self, shape, pos, tolerance=8):
        """Return insertion index and projection for the single selected polygon."""
        if (self.mode != 'edit' or shape.shape_type != 'polygon' or not shape.selected
                or len(self.selected_shape) != 1 or len(shape.pointslist) < 3):
            return None
        # Keep the existing vertex target priority, including tiny-shape body hits.
        if self.find_closest_vertex(pos, shape.pointslist, 8) >= 0:
            return None
        # Include the exact screen-pixel boundary despite transform rounding.
        limit_squared = self._screen_tolerance(tolerance) ** 2 * (1 + 1e-12)
        closest = None
        min_distance = float('inf')
        for index, end in enumerate(shape.pointslist):
            start = shape.pointslist[index - 1]
            dx, dy = end.x() - start.x(), end.y() - start.y()
            length_squared = dx * dx + dy * dy
            if length_squared == 0:
                continue
            t = max(0., min(1., ((pos.x()-start.x())*dx + (pos.y()-start.y())*dy) / length_squared))
            projection = QPointF(start.x() + t*dx, start.y() + t*dy)
            distance = (pos.x()-projection.x())**2 + (pos.y()-projection.y())**2
            if distance <= limit_squared and distance < min_distance:
                min_distance = distance
                # Insert before this edge's end; index 0 splits the closing edge.
                closest = (index, projection)
        if closest is not None and self.find_closest_vertex(closest[1], shape.pointslist, 8) >= 0:
            return None
        return closest

    def get_shape_at_pos(self, pos, tolerance=8, polygon_edges=False):
        return next(self.iter_shape_hits(pos,tolerance,polygon_edges),(None,None))

    def iter_shape_hits(self, pos, tolerance=8, polygon_edges=False):
        if pos is None:
            return
        margin = self._screen_tolerance(max(tolerance, 8))
        region = QtCore.QRectF(pos.x()-margin,pos.y()-margin,2*margin,2*margin)
        for shape in reversed(self._spatial_candidates(region)):
            if not shape.visible:
                continue
            if not shape.visual_bounds(scale=None if display.current.auto_scale else self.scale_factor).adjusted(-margin, -margin, margin, margin).contains(pos):
                continue
            if shape.shape_type == 'point' and len(shape.pointslist) == 1:
                radius = max(self._screen_tolerance(tolerance), display.point_radius(self.scale_factor, shape.base_point_size))
                if QLineF(pos, shape.pointslist[0]).length() <= radius:
                    yield shape, 'point'; continue
            elif shape.shape_type == 'line' and len(shape.pointslist) == 2:
                # At low zoom, endpoint targets must not cover the whole short line.
                endpoint_pixels = min(tolerance, QLineF(*shape.pointslist).length() * self.scale_factor * .2)
                vertex = self.find_closest_vertex(pos, shape.pointslist, endpoint_pixels)
                midpoint = shape.get_center()
                if vertex >= 0 and QLineF(pos, shape.pointslist[vertex]).length() < QLineF(pos, midpoint).length():
                    yield shape, vertex; continue
                if self._segment_distance_squared(pos, *shape.pointslist) <= self._screen_tolerance(tolerance)**2:
                    yield shape, 'mid'; continue
            elif shape.shape_type in ('polygon', 'rectangle', 'rotated_rectangle'):
                inside = self.is_pos_inside_shape(shape, pos)
                vertex = self._edit_vertex(shape, pos, tolerance, inside) if shape.selected or shape.shape_type != 'polygon' else -1
                if shape.shape_type == 'rotated_rectangle':
                    handle = shape.get_rotation_handle_position()
                    near, distance = self.is_point_near_handle(pos, handle, 8)
                    if (near and (not inside or distance < QLineF(pos, shape.get_center()).length())
                            and (vertex < 0 or distance < QLineF(pos, shape.pointslist[vertex]).length())):
                        yield shape, 'rotation_handle'; continue
                if vertex >= 0:
                    yield shape, vertex; continue
                if polygon_edges and self._polygon_edge_target(shape, pos) is not None:
                    yield shape, 'edge'; continue
                if inside:
                    yield shape, 'inside' if shape.shape_type == 'rotated_rectangle' else None; continue
        return

    def is_point_near_handle(self, pos, handle_pos, tolerance=5):
        """检查点是否接近控制点"""
        if pos is None or handle_pos is None:
            return False, float('inf')
            
        tolerance = self._screen_tolerance(tolerance)
        dist = _calculate_distance_numba(pos.x(), pos.y(), handle_pos.x(), handle_pos.y())
        return dist <= tolerance, dist

    def find_closest_vertex(self, pos, vertices, tolerance=5):
        """查找最近的顶点"""
        if not vertices:
            return -1
            
        tolerance = self._screen_tolerance(tolerance)
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
                    vertices_x, vertices_y = shape.cached_vertices()
                    
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

        epsilon = self._screen_tolerance(epsilon)
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
        exposed = option.exposedRect if option is not None else self.boundingRect()
        if exposed.isEmpty():
            exposed = self.boundingRect()
        full_repaint = exposed.contains(self.boundingRect())
        font = painter.font()
        paint_scale = None if display.current.auto_scale else display.transform_scale(painter.worldTransform())
        try:
            # Stable stacking order must match reverse-order hit testing.
            candidates = self.shapes if full_repaint else self._spatial_candidates(exposed, font, paint_scale)
            for shape in candidates:
                if shape.visible and (full_repaint or shape.visual_bounds(font, paint_scale).intersects(exposed)):
                    try:
                        shape.paint(painter, option, widget)
                    except Exception as e:
                        print(f"Unable to paint shape: {e}")
                shape._dirty = False

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
        scale = self.scale_factor if display.current.auto_scale else display.transform_scale(painter.worldTransform())
        pen_color = QColor(255, 255, 255, 64)
        
        pen_width = (max(int(2 / scale), 1) if display.current.auto_scale else 2/scale) 
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
            polygon = shape.cached_polygon()
            painter.drawPolygon(polygon)
        elif shape.shape_type == 'line' and len(shape.pointslist) == 2:
            painter.drawLine(shape.pointslist[0], shape.pointslist[1])
        elif shape.shape_type == 'rotated_rectangle' and len(shape.pointslist) == 4:
            polygon = shape.cached_polygon()
            painter.drawPolygon(polygon)  # 绘制旋转矩形

    def draw_creation_guides(self, painter):

        if not self.current_shape or self.create_shape_type is None:
            return
        """绘制创建形状时的辅助线和预览"""
        scale = self.scale_factor if display.current.auto_scale else display.transform_scale(painter.worldTransform())
        pen = QtGui.QPen(QtGui.QColor(255, 255, 255), max(int(2/scale), 1) if display.current.auto_scale else 2/scale, QtCore.Qt.DashLine)
        painter.setPen(pen)

        if self.create_shape_type == 'rectangle' and len(self.current_shape.pointslist) == 2:
            rect = QtCore.QRectF(self.current_shape.pointslist[0], self.current_shape.pointslist[1])
            painter.drawRect(rect)
 
        elif self.create_shape_type == 'rotated_rectangle':
            if self.rotated_rect_stage == 1 and len(self.current_shape.pointslist) == 1:
                # 第一阶段：绘制拖动线段
                pen.setWidthF((max(int(2 / scale), 1) if display.current.auto_scale else 2/scale) )
                painter.setPen(pen)
                if self.current_mouse_pos:
                    painter.drawLine(self.current_shape.pointslist[0], self.current_mouse_pos)
                    
                    # 高亮显示第一个点
                    point_size = (max(int(6/scale), 2) if display.current.auto_scale else 6/scale)  # 确保是整数
                    painter.setBrush(QtGui.QBrush(QtGui.QColor(255, 255, 255)))
                    painter.drawEllipse(self.current_shape.pointslist[0], point_size, point_size)
            
            elif self.rotated_rect_stage == 2 and len(self.current_shape.pointslist) >= 4:
                # 第二阶段：绘制整个旋转矩形预览
                polygon = QtGui.QPolygonF(self.current_shape.pointslist)
                
                # 使用更明显的样式绘制预览
                pen = QtGui.QPen(QtGui.QColor(255, 255, 255), (max(int(2/scale), 1) if display.current.auto_scale else 2/scale), QtCore.Qt.DashLine)
                painter.setPen(pen)
                painter.setBrush(QtGui.QBrush(QtGui.QColor(0, 0, 0, 60)))
                painter.drawPolygon(polygon)
                # 绘制四个角
                point_size = (max(int(6/scale), 2) if display.current.auto_scale else 6/scale)  # 确保是整数
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
                point_size = 4/scale  # 更大的点尺寸
                painter.setBrush(QtGui.QBrush(QtGui.QColor(255, 255, 255, 180)))
                for point in points:
                    painter.drawEllipse(point, point_size, point_size)

        elif self.create_shape_type == 'line' and len(self.current_shape.pointslist) == 1:
            if self.current_mouse_pos:
                painter.drawLine(self.current_shape.pointslist[0], self.current_mouse_pos)

    def set_selected_shapes(self, shapes):
        # Canvas owns the selection; equal geometry is not object identity.
        existing = {id(shape) for shape in self.shapes}
        shapes = list({id(shape): shape for shape in shapes if id(shape) in existing}.values())
        chosen = {id(shape) for shape in shapes}
        previous = {id(shape) for shape in self.selected_shape}
        region = QtCore.QRectF()
        changed = False
        for shape in self.shapes:
            selected = id(shape) in chosen
            if shape.selected != selected:
                region = region.united(shape.visual_bounds(
                    scale=None if display.current.auto_scale else self.scale_factor))
                shape.selected = selected
                shape._dirty = True
                changed = True
        self.selected_shape = shapes
        if changed or previous != chosen:
            self.shapeSelected.emit(shapes)
        if changed:
            self.update(region)

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
        # self.save_state()

    def create_rotated_rectangle(self):
        """创建旋转矩形模式"""
        self.mode = 'create'
        self.create_shape_type = 'rotated_rectangle'
        self.current_shape = Shape(shape_type='rotated_rectangle',scale_factor=self.scale_factor)
        self.drawing = False
        # self.save_state()

    def create_rectangle(self):
        """创建矩形模式"""
        self.mode = 'create'
        self.create_shape_type = 'rectangle' 
        self.current_shape = Shape(shape_type='rectangle',scale_factor=self.scale_factor)
        self.drawing = False
        # self.save_state()

    def create_line(self):
        """创建线条模式"""
        self.mode = 'create'
        self.create_shape_type = 'line'
        self.current_shape = Shape(shape_type='line',scale_factor=self.scale_factor)
        self.drawing = False
        # self.save_state()

    def create_point(self):
        """创建点模式"""
        self.mode = 'create'
        self.create_shape_type = 'point'
        self.current_shape = Shape(shape_type='point',scale_factor=self.scale_factor)
        self.drawing = False
        # self.save_state()

    def finish_shape(self):
        """完成形状创建"""
        if self.current_shape:
            shape = self.current_shape
            width, height = self.image_size.width(), self.image_size.height()
            if shape.shape_type == 'polygon':
                points = shape.pointslist
                while len(points) > 1 and (points[-1] == points[0] or points[-1] == points[-2]):
                    points.pop()
                if len(points) < MIN_POLYGON_VERTICES or len({(p.x(), p.y()) for p in points}) < MIN_POLYGON_VERTICES:
                    self._geometry_notice('A polygon requires at least 5 points.')
                    return False
                from annotation_io import validate_polygon_export
                content = '0 ' + ' '.join(f'{p.x()/width:.6f} {p.y()/height:.6f}' for p in points)
                try:
                    validate_polygon_export(content, width, height, 'new polygon')
                except ValueError as error:
                    self._geometry_notice(str(error))
                    return False
            elif shape.shape_type in ('rectangle', 'rotated_rectangle'):
                from annotation_io import validate_rectangle_export
                if shape.shape_type == 'rectangle':
                    p1, p2 = shape.pointslist
                    line = (f'0 {(p1.x()+p2.x())/(2*width):.6f} '
                            f'{(p1.y()+p2.y())/(2*height):.6f} '
                            f'{abs(p2.x()-p1.x())/width:.6f} '
                            f'{abs(p2.y()-p1.y())/height:.6f}')
                else:
                    line = '0 ' + ' '.join(f'{p.x()/width:.17g} {p.y()/height:.17g}'
                                         for p in shape.pointslist)
                try:
                    validate_rectangle_export([shape], line, shape.shape_type,
                                              width, height, 'new rectangle')
                except (ValueError, IndexError) as error:
                    self._geometry_notice(str(error))
                    return False
            self.save_state()
            self.shapes.append(self.current_shape)
            self.shapeCreated.emit(self.current_shape)
            # self.save_state()
            self.current_shape = None
            self.drawing = False
            self.create_shape_type = self.create_shape_type
            self.shapesChanged.emit()
            self.update()
            return True
        return False

###############################################
############ 撤销回退机制的实现
############ the revocation/undo mechanism
###############################################
    # def save_state(self):
    #     """保存当前形状状态以支持撤销操作，手动创建新的形状对象而不是使用deepcopy"""
    #     try:
    #         # 创建形状的简化表示，只包含可安全序列化的数据
    #         shapes_state = []
    #         for shape in self.shapes:
    #             try:
    #                 # 安全地收集有效点
    #                 valid_points = []
    #                 for p in shape.pointslist:
    #                     if p is not None and isinstance(p, QPointF):
    #                         try:
    #                             valid_points.append(QPointF(p.x(), p.y()))
    #                         except Exception as e:
    #                             print(f"无法复制点: {e}")
    #                             continue

    #                 # 检查形状是否有效
    #                 if not valid_points:
    #                     print(f"跳过无效形状: 没有有效的点")
    #                     continue

    #                 # 确保多边形至少有3个点，或者其他形状符合要求
    #                 if (shape.shape_type == 'polygon' and len(valid_points) < 3) or \
    #                         (shape.shape_type == 'rectangle' and len(valid_points) != 2) or \
    #                         (shape.shape_type == 'line' and len(valid_points) != 2) or \
    #                         (shape.shape_type == 'rotated_rectangle' and len(valid_points) != 4) or \
    #                         (shape.shape_type == 'point' and len(valid_points) != 1):
    #                     print(f"跳过无效形状: {shape.shape_type} 点数量不正确")
    #                     continue

    #                 # 为每个形状创建一个新实例
    #                 new_shape = Shape(
    #                     label=shape.label,
    #                     classnum=shape.classnum,
    #                     pointslist=valid_points,
    #                     shape_type=shape.shape_type,
    #                     group_id=shape.group_id

    #                 )
    #                 # 复制必要的其他属性
    #                 new_shape.visible = shape.visible
    #                 new_shape._selected = shape._selected
    #                 new_shape.rotated_angle = shape.rotated_angle
    #                 new_shape._show_group_id = shape._show_group_id
    #                 new_shape.feature_results = shape.feature_results
    #                 new_shape.scale_factor = shape.scale_factor

    #                 # 添加到状态列表
    #                 shapes_state.append(new_shape)
    #             except Exception as e:
    #                 print(f"处理形状时出错: {e}")
    #                 continue  # 跳过这个形状

    #         # 存储状态
    #         self.undo_stack.append(shapes_state)

    #         # 限制撤销栈大小
    #         if len(self.undo_stack) > 4:
    #             self.undo_stack.pop(0)

    #     except Exception as e:
    #         print(f"保存状态时出错: {e}")
    #         # 错误处理 - 可能需要清空撤销栈以避免进一步问题
    #         self.undo_stack = []

    # def undo(self):
    #     """安全地恢复到上一个保存的状态"""
    #     if not self.undo_stack:
    #         return

    #     try:
    #         # 恢复上一个状态
    #         previous_shapes = self.undo_stack.pop()
    #         scene = self.scene()

    #         if not scene:
    #             print("警告：当前画布没有关联场景")
    #             return

    #         # 清除当前状态
    #         self.selected_shape = []
    #         self.hovered_shape = None

            
    #         # 清除场景中的所有形状
    #         for shape in self.shapes.copy():
    #             try:
    #                 if shape.scene() == scene:
    #                     scene.removeItem(shape)
    #                 self.shapes.remove(shape)
    #             except Exception as e:
    #                 print(f"从场景移除形状时出错: {e}")
            
    #         # 确保形状列表为空
    #         self.shapes.clear()
            
    #         # 为每个保存的形状创建新的形状对象
    #         for saved_shape in previous_shapes:
    #             try:
    #                 # 创建新的形状对象，保持原有属性
    #                 new_shape = Shape(
    #                     label=saved_shape.label,
    #                     classnum=saved_shape.classnum,
    #                     pointslist=[QPointF(p.x(), p.y()) for p in saved_shape.pointslist],
    #                     shape_type=saved_shape.shape_type,
    #                     group_id=saved_shape.group_id
    #                 )
                    
    #                 # 复制其他属性
    #                 new_shape.visible = saved_shape.visible
    #                 new_shape._selected = saved_shape._selected
    #                 new_shape.rotated_angle = saved_shape.rotated_angle
    #                 new_shape._show_group_id = saved_shape._show_group_id
    #                 new_shape.feature_results = saved_shape.feature_results
                    
    #                 # 只添加到列表和场景，不设置父项
    #                 self.shapes.append(new_shape)
    #                 # scene.addItem(new_shape)
    #                 # 移除这一行: new_shape.setParentItem(self)
    #             except Exception as e:
    #                 print(f"恢复形状时出错: {e}")
    #                 continue
                    
    #         # 重置交互状态
    #         self.dragging_point = False
    #         self.moving_shape = False
    #         self.rotating = False
    #         self.scaling_rotated_rectangle = False
            
    #         # 更新界面
    #         self.shapesChanged.emit()
    #         self.update()
                        
    #     except Exception as e:
    #         print(f"撤销操作出错: {e}")
    #         self.undo_stack = []
    #         self.update()


###############################################
############ 新撤销回退机制的实现-260307
############ the revocation/undo mechanism
###############################################
    @property
    def undo_stack(self):
        return self._history.undo

    @undo_stack.setter
    def undo_stack(self, value):
        self._history.undo = value

    @property
    def redo_stack(self):
        return self._history.redo

    def save_state(self, commit=True):
        if commit and self._edit_before is not None:
            self._finish_geometry_edit()
        state = self._history.capture(self.shapes)
        if commit:
            self._push_undo_state(state, clear_redo=False)
            self._history_pending = state
        return state

    def _push_undo_state(self, state, clear_redo=True):
        if not self.undo_stack or self.undo_stack[-1] != state:
            self.undo_stack.append(state)
        if clear_redo:
            self.redo_stack.clear()
            self._history.trim()

    def _commit_pending_history(self):
        if self._restoring_history or self._history_pending is None:
            return
        pending = self._history_pending
        self._history_pending = None
        # A changed object count already proves a real edit (add/delete). Avoid
        # copying the remaining scene just to establish that it is not a no-op.
        # The normal shapesChanged handlers still validate measurements in full.
        changed = len(self.shapes) != len(pending)
        if changed or not self._history.same_content(self._history.capture(self.shapes), pending):
            self.redo_stack.clear()
        elif self.undo_stack and self.undo_stack[-1] is pending:
            self.undo_stack.pop()
        self._history.trim()

    @staticmethod
    def _coordinates(shape):
        return tuple((p.x(), p.y()) for p in shape.pointslist)

    def _prepare_geometry_edit(self, event):
        if not event.buttons() & QtCore.Qt.LeftButton:
            return False
        if not (self.moving_shape or self.dragging_point or self.rotating or self.scaling_rotated_rectangle):
            return False
        if not self.selected_shape:
            return False
        if self._edit_before is None:
            # Ignore click jitter, in screen pixels. Do not evict history until commit.
            if QLineF(self.drag_start_pos, event.pos()).length() * self.scale_factor < 3:
                return False
            self._edit_before = self.save_state(commit=False)
            if self._edit_before is None:
                return False
            self._edit_original = tuple((s, self._coordinates(s)) for s in self.selected_shape)
            self._move_applied = QPointF()
        return True

    def _finish_geometry_edit(self):
        had_preview = self._edit_before is not None
        if had_preview:
            changed = any(len(s.pointslist) != len(before) or any(
                abs(p.x() - x) > 1e-9 or abs(p.y() - y) > 1e-9
                for p, (x, y) in zip(s.pointslist, before))
                for s, before in self._edit_original)
            if changed:
                self._push_undo_state(self._edit_before)
            else:
                # A round trip can leave floating-point noise; restore exact input.
                for s, before in self._edit_original:
                    if self._coordinates(s) != before:
                        s.pointslist = [QtCore.QPointF(x, y) for x, y in before]
        self._edit_before = None
        self._edit_original = ()
        self._reset_edit_motion()
        return had_preview

    def _reset_edit_motion(self):
        self.moving_shape = self.dragging_point = self.rotating = self.scaling_rotated_rectangle = False
        self.rotating_shape = self.scaling_shape = None
        self.hovered_point_index = None
        self.setCursor(QtCore.Qt.ArrowCursor)

    def _select_edit_target(self, event, shape, preserve_group=False):
        if event.modifiers() & QtCore.Qt.ControlModifier:
            selected = list(self.selected_shape)
            if any(s is shape for s in selected):
                selected = [s for s in selected if s is not shape]
            else:
                selected.append(shape)
            self.set_selected_shapes(selected)
            self.update()
            return False  # Ctrl changes selection; never starts a geometry edit.
        if preserve_group and any(s is shape for s in self.selected_shape):
            self.set_selected_shapes(self.selected_shape)
        else:
            self.set_selected_shapes([shape])
        self.drag_start_pos = event.pos()
        return True

    def undo(self):
        return self._restore_history(self.undo_stack, self.redo_stack)

    def redo(self):
        return self._restore_history(self.redo_stack, self.undo_stack)

    def _restore_history(self, source, destination):
        self._finish_geometry_edit()
        self._commit_pending_history()
        if not source:
            return False
        current = self._history.capture(self.shapes)
        previous = source[-1]
        # Prepare every object that can allocate or deep-copy before touching the
        # live scene or either history stack.
        existing = {getattr(shape, '_history_id', None): shape for shape in self.shapes}
        prepared = []
        for state in previous:
            points = [QPointF(x, y) for x, y in state['pointslist']]
            payloads = {key: copy.deepcopy(state[key]) for key in
                        ('feature_results', '_measurement_scale', 'polygon_audit')}
            shape = existing.get(state['_history_id'])
            if shape is None:
                shape = Shape(label=state['label'], classnum=state['classnum'],
                              pointslist=points, shape_type=state['shape_type'],
                              group_id=state['group_id'])
                shape._history_id = state['_history_id']
            prepared.append((state, points, payloads, shape))
        original_shapes = list(self.shapes)
        original_ids = {id(shape) for shape in original_shapes}
        shape_backups = [(shape, shape.__dict__.copy()) for shape in original_shapes]
        canvas_backup = self.__dict__.copy()
        for key in ('_shape_by_id', '_measurement_dirty', '_measurement_removed'):
            canvas_backup[key] = getattr(self, key).copy()
        source_backup, destination_backup = list(source), list(destination)
        restored = []
        self._restoring_history = True
        self._history_generation += 1
        try:
            for state, points, payloads, shape in prepared:
                measurement_payload_changed = (shape.feature_results != state['feature_results']
                    or getattr(shape, '_measurement_key', None) != state['_measurement_key']
                    or getattr(shape, 'measurement_error', None) != state['measurement_error'])
                if id(shape) in original_ids and (self._coordinates(shape) != state['pointslist']
                                                  or shape.shape_type != state['shape_type']):
                    shape.shape_type = state['shape_type']
                    shape.pointslist = points
                for key in ('label','classnum','group_id','visible','rotated_angle',
                            '_show_group_id','unit','_show_points'):
                    if getattr(shape,key) != state[key]:
                        setattr(shape,key,state[key])
                for key in ('feature_results','_measurement_scale','polygon_audit'):
                    if getattr(shape,key,None) != state[key]:
                        setattr(shape,key,payloads[key])
                # Keep the saved provenance, not a fabricated fresh stamp. The normal
                # commit refresh and exports still compare it against geometry/scale.
                shape._measurement_key = state['_measurement_key']
                shape.measurement_error = state['measurement_error']
                if measurement_payload_changed:
                    self.measurement_changed(shape)
                shape.selected = False
                shape._history_epoch = self._history_generation
                shape.set_scale_factor(self.scale_factor)
                restored.append(shape)
            if len(self.shapes) != len(restored) or any(a is not b for a,b in zip(self.shapes,restored)):
                self.shapes[:] = restored
            self.selected_shape = []
            self.hovered_shape = self._last_hover_shape = None
            self._reset_edit_motion()
            self.set_mode('edit')
            self.drawing = False
            self.current_shape = None
            self.rotated_rect_stage = 0
            destination.append(current)
            source.pop()
            self._history.trim()
            self.shapeSelected.emit([])
            self.shapesChanged.emit()
            self.update()
        except Exception:
            source[:] = source_backup
            destination[:] = destination_backup
            for shape, backup in shape_backups:
                shape.__dict__.clear()
                shape.__dict__.update(backup)
            self.shapes[:] = original_shapes
            self.__dict__.clear()
            self.__dict__.update(canvas_backup)
            self._spatial.members_dirty = True
            raise
        finally:
            self._restoring_history = False
        return True

    def _polygon_add_cursor(self):
        """A fixed screen-size arrow-plus, distinct from vertex-edit crosshairs."""
        if not hasattr(self, '_add_vertex_cursor'):
            screen = QtGui.QGuiApplication.primaryScreen()
            ratio = screen.devicePixelRatio() if screen is not None else 1.
            pixmap = QtGui.QPixmap(round(32 * ratio), round(32 * ratio))
            pixmap.setDevicePixelRatio(ratio)
            pixmap.fill(QtCore.Qt.transparent)
            painter = QtGui.QPainter(pixmap)
            painter.setRenderHint(QtGui.QPainter.Antialiasing)
            arrow = QtGui.QPainterPath(QPointF(3, 2))
            for point in ((3, 20), (8, 15), (12, 23), (16, 21), (12, 13), (20, 13)):
                arrow.lineTo(QPointF(*point))
            arrow.closeSubpath()
            painter.setPen(QtGui.QPen(QtCore.Qt.white, 2, QtCore.Qt.SolidLine, QtCore.Qt.RoundCap, QtCore.Qt.RoundJoin))
            painter.setBrush(QtCore.Qt.black)
            painter.drawPath(arrow)
            segments = ((24, 19, 24, 29), (19, 24, 29, 24))
            # A white outline keeps the black cursor legible over any image.
            for color, width in ((QtCore.Qt.white, 3.5), (QtCore.Qt.black, 1.5)):
                painter.setPen(QtGui.QPen(color, width, QtCore.Qt.SolidLine, QtCore.Qt.RoundCap))
                for segment in segments:
                    painter.drawLine(QtCore.QLineF(*segment))
            painter.end()
            self._add_vertex_cursor = QtGui.QCursor(pixmap, 3, 2)
        return self._add_vertex_cursor

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
        
        elif self.mode == 'edit':
            old = getattr(self, '_last_hover_shape', None)
            region = old.visual_bounds() if old is not None else QtCore.QRectF()
            if old is not None:
                old.hovered_point_index = None
            polygon_edges = not (event.modifiers() & QtCore.Qt.ControlModifier) and event.modifiers() != QtCore.Qt.AltModifier
            shape, part = self.get_shape_at_pos(pos, polygon_edges=polygon_edges)
            self.hovered_shape = self._last_hover_shape = shape
            self.hovered_point_index = part if isinstance(part, int) else None
            if shape is not None:
                shape.hovered_point_index = self.hovered_point_index
                region = region.united(shape.visual_bounds())
            cursor = (QtGui.QCursor(QtCore.Qt.CrossCursor) if isinstance(part, int) else
                      self._polygon_add_cursor() if part == 'edge' else
                      QtGui.QCursor(QtCore.Qt.OpenHandCursor if shape is not None else QtCore.Qt.ArrowCursor))
            self.setCursor(cursor)
            if not region.isEmpty():
                self.update(region)
        super(Canvas, self).hoverMoveEvent(event)

    def hoverMoveEvent_rotated_rectangle(self, event):
        pos = event.pos()
        cursor = QtCore.Qt.ArrowCursor
        hovered = False
        self.hovered_shape = None
        self.hovered_point_index = None
        shape, index = self.get_shape_at_pos(pos) # 获取鼠标位置附近的形状和点索引    
        if shape is None:
            return
        if shape.visible and index is not None:
            hovered = True
            self.hovered_shape = shape
            shape.hovered_point_index = None
            self.hovered_point_index = None
            if index not in ['rotation_handle', 'inside']:
                self.hovered_point_index = index
                shape.hovered_point_index = index
        # The caller updates the union of the previous and current hover bounds.

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
        
        if ab_length < 1e-12:  # 防止除零错误
            return None, None
            
        # 计算AB的单位方向向量
        unit_ab = QtCore.QPointF(ab_vector.x() / ab_length, ab_vector.y() / ab_length)
        
        # 计算垂直于AB的单位向量 (逆时针旋转90度)
        perp_unit_ab = QtCore.QPointF(-unit_ab.y(), unit_ab.x())
        
        # 计算从点A到点M的向量
        am_vector = QtCore.QPointF(mouse_pos.x() - point_a.x(), mouse_pos.y() - point_a.y())
        
        # 计算点M到线AB的垂直距离（带符号）
        height = am_vector.x() * perp_unit_ab.x() + am_vector.y() * perp_unit_ab.y()
        minimum = self._minimum_rectangle_size()
        if abs(height) < minimum:
            height = -minimum if height < 0 else minimum
        
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
            if event.button() == QtCore.Qt.LeftButton and event.modifiers() == QtCore.Qt.AltModifier:
                candidates = [shape for shape, part in self.iter_shape_hits(pos)]
                if candidates:
                    current = self.selected_shape[0] if len(self.selected_shape) == 1 else None
                    index = next((i for i,shape in enumerate(candidates) if shape is current), -1)
                    self.set_selected_shapes([candidates[(index+1) % len(candidates)]])
                event.accept()
                return
            polygon_edges = (self.mode == 'edit' and event.button() == QtCore.Qt.LeftButton
                             and not (event.modifiers() & QtCore.Qt.ControlModifier))
            clicked_shape, clicked_part = self.get_shape_at_pos(pos, tolerance=8, polygon_edges=polygon_edges)

            if clicked_shape and clicked_shape.shape_type == 'rotated_rectangle':
                self.handle_editmode_mouse_press_rotated_rectangle(event, clicked_shape, clicked_part)
            elif clicked_shape and clicked_shape.shape_type == 'line':
                self.handle_editmode_mouse_press_line(event, clicked_shape, clicked_part)
            elif clicked_shape and clicked_shape.shape_type == 'point' and clicked_part == 'point':
                if event.button() == QtCore.Qt.LeftButton and self._select_edit_target(event, clicked_shape, preserve_group=True):
                    self.moving_shape = True
                event.accept()

            else:

                self.handle_editmode_mouse_press(event, (clicked_shape, clicked_part))
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
                    while len(self.current_shape.pointslist) < 4:
                        self.current_shape.pointslist.append(None)
                    self.current_shape.pointslist[2] = p3
                    self.current_shape.pointslist[3] = p4
      
                    
                    # 计算旋转角度
                    edge_vector = QtCore.QLineF(p1, p2)
                    angle = edge_vector.angle()
                    self.current_shape.sync_rotated_angle()
                    
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
            if pos != self.bounded_point(pos):
                return
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
                    first_point = self.current_shape.pointslist[0]
                    if self.is_close_enough(pos, first_point, tolerance=8):
                        self.finish_shape()
                    else:
                        self.current_shape.pointslist.append(pos)
                        self.update()  # 刷新画布以显示新线

    def handle_editmode_mouse_press_rotated_rectangle(self, event, clicked_shape, clicked_part):
        if event.button() != QtCore.Qt.LeftButton:
            return
        if not self._select_edit_target(event, clicked_shape, preserve_group=clicked_part == 'inside'):
            return
        if isinstance(clicked_part, int):
            self.scaling_rotated_rectangle = True
            self.scaling_shape = clicked_shape
            self.hovered_point_index = clicked_part
            self.scaling_anchor_index = clicked_part
            self.scaling_fixed_index = (clicked_part + 2) % 4
            self.scaling_fixed_point = QtCore.QPointF(clicked_shape.pointslist[self.scaling_fixed_index])
        elif clicked_part == 'rotation_handle':
            self.rotation_start_pos = event.pos()
            self.hovered_shape = clicked_shape
            self.rotating = True
            self.rotating_shape = clicked_shape
            self.rotation_center = clicked_shape.get_center()
        elif clicked_part == 'inside':
            self.moving_shape = True
            self.setCursor(QtCore.Qt.ClosedHandCursor)

    def handle_editmode_mouse_press_line(self, event, clicked_shape, clicked_part):
        if event.button() != QtCore.Qt.LeftButton:
            return
        if not self._select_edit_target(event, clicked_shape, preserve_group=clicked_part == 'mid'):
            return
        if isinstance(clicked_part, int):
            self.hovered_point_index = clicked_part
            self.dragging_point = True
            self.setCursor(QtCore.Qt.CrossCursor)
        elif clicked_part == 'mid':
            self.moving_shape = True
            self.setCursor(QtCore.Qt.ClosedHandCursor)

    def handle_editmode_mouse_press(self, event, hit=None):
        pos = event.pos()
        shape, part = self.get_shape_at_pos(pos) if hit is None else hit
        if event.button() == QtCore.Qt.LeftButton:
            if shape is None:
                self.set_selected_shapes([])
                return
            if event.modifiers() & QtCore.Qt.ControlModifier:
                self._select_edit_target(event, shape)
                return
            # Insertion belongs to the actual hit polygon, never another selected one.
            if part in (None, 'edge'):
                edge = self._polygon_edge_target(shape, pos)
                if edge is not None:
                    self.save_state()
                    line_index, projection = edge
                    shape.add_point(line_index, projection)
                    self.set_selected_shapes([shape])
                    self.shapesChanged.emit()
                    self.update(shape.visual_bounds())
                    return
            self._select_edit_target(event, shape, preserve_group=not isinstance(part, int))
            if isinstance(part, int):
                self.hovered_point_index = part
                self.dragging_point = True
                self.setCursor(QtCore.Qt.CrossCursor)
            else:
                self.moving_shape = True
                self.setCursor(QtCore.Qt.ClosedHandCursor)
        elif event.button() == QtCore.Qt.RightButton:
            if shape is None:
                self.set_selected_shapes([])
            elif shape.shape_type == 'polygon' and shape.selected:
                if event.modifiers() & QtCore.Qt.ControlModifier:
                    self.delete_polygon_multiple_points(pos, shape)
                else:
                    self.delete_polygon_single_point(pos, shape)

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
        distances = [(i, dist) for i, dist in distances if dist <= radius]
        points_in_radius = len(distances)
        if not distances:
            return []

        # 根据局部密度确定要删除的点数量
        # 局部密度越高，删除的点越多，但在count_range范围内
        min_count, max_count = count_range
        density_factor = min(1.0, points_in_radius / 10.0)  # 假设局部区域内有10个点为高密度

        # 计算要删除的点数量，在count_range范围内
        points_to_remove = int(min_count + density_factor * (max_count - min_count))

        # 限制删除点的数量，不能太多以至于破坏多边形
        max_points_to_remove = max(0, min(points_to_remove,
                                           len(shape.pointslist) - MIN_POLYGON_VERTICES))

        # 返回要删除的点的索引列表
        return [idx for idx, _ in distances[:max_points_to_remove]]

    def delete_polygon_multiple_points(self, pos, shape=None):
        shape = shape if shape is not None else self.get_shape_at_pos(pos)[0]
        if (shape is None or shape.shape_type != 'polygon' or not shape.selected
                or not any(s is shape for s in self.shapes)):
            return False
        indices = self.get_multiple_points_of_a_polygon_at_pos(pos, shape)
        if not indices:
            return False
        self.save_state()
        for index in sorted(indices, reverse=True):
            shape.remove_point(index)
        self.shapesChanged.emit()
        self.update()
        return True

    def delete_polygon_single_point(self, pos, shape=None):
        shape = shape if shape is not None else self.get_shape_at_pos(pos, tolerance=10)[0]
        if (shape is None or shape.shape_type != 'polygon' or not shape.selected
                or len(shape.pointslist) <= MIN_POLYGON_VERTICES
                or not any(s is shape for s in self.shapes)):
            if shape is not None and shape.shape_type == 'polygon' and len(shape.pointslist) == MIN_POLYGON_VERTICES:
                self._geometry_notice('A polygon must contain at least 5 points.')
            return False
        index = self.find_closest_vertex(pos, shape.pointslist, tolerance=10)
        if index < 0:
            return False
        self.save_state()
        shape.remove_point(index)
        self.shapesChanged.emit()
        self.update()
        return True

###############################################
############ 关于鼠标事件代码===========Move
###############################################

    
    def mouseMoveEvent(self, event):
        pos = event.pos()  # 确保 pos 在方法一开始就被定义
        self.current_mouse_pos = pos  # 更新当前鼠标位置

        if self.mode == 'create' and self.drawing:
            if self.create_shape_type == 'rectangle':
                first = self.current_shape.pointslist[0]
                previous = (self.current_shape.pointslist[1]
                            if len(self.current_shape.pointslist) == 2 else None)
                pos = self._clamp_rectangle_corner(first, pos, previous)
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
            if not self._prepare_geometry_edit(event):
                super(Canvas, self).mouseMoveEvent(event)
                return
            shapes_to_update = []
            old_region = QtCore.QRectF()
            for selected in self.selected_shape:
                old_region = old_region.united(selected.visual_bounds(scale=None if display.current.auto_scale else self.scale_factor))
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
                self.scaling_shape.scale_rotated_rectangle(
                    anchor_index, moving_point, fixed_point, self._minimum_rectangle_size())
                self.scaling_shape.update_shape()  # 只更新当前形状

            ### 对于旋转矩形和其他shape的移动事件
            elif self.moving_shape and self.selected_shape:

                delta = pos - self.drag_start_pos
                # Clamp a shared translation using Point bounds only. Other types
                # retain geometry and relative offsets; existing annotations are not normalized.
                points = [before[0] for shape,before in self._edit_original
                          if shape.shape_type == 'point' and len(before) == 1]
                if points:
                    low_x,high_x = max(-x for x,y in points), min(self.image_size.width()-x for x,y in points)
                    low_y,high_y = max(-y for x,y in points), min(self.image_size.height()-y for x,y in points)
                    if low_x > high_x or low_y > high_y:
                        delta = QPointF()
                    else:
                        delta = QPointF(min(max(delta.x(),low_x),high_x), min(max(delta.y(),low_y),high_y))
                dx,dy = delta.x()-self._move_applied.x(), delta.y()-self._move_applied.y()
                self._move_applied = delta

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
                if shape.shape_type == 'rectangle' and len(shape.pointslist) == 2:
                    pos = self._clamp_rectangle_corner(shape.pointslist[1-index], pos,
                                                       shape.pointslist[index])
                shape.pointslist[index] = pos
                shape._dirty = True
                shape.update()  # 只更新当前形状
            
           
        # 如果有形状需要更新，只更新这些形状
            if shapes_to_update:
                region = old_region
                for changed in shapes_to_update:
                    region = region.united(changed.visual_bounds(scale=None if display.current.auto_scale else self.scale_factor))
                self.update(region)
            

            
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

                if moved_distance <= tolerance and self.create_shape_type == 'line':
                    # 鼠标没有移动，不创建形状
                    self.current_shape = None  # 重置当前形状
                    self.drawing = False
                    self.update()
                    return  # 直接返回，不执行后续创建逻辑


                if self.create_shape_type == 'rectangle':
                    first = self.current_shape.pointslist[0]
                    previous = (self.current_shape.pointslist[1]
                                if len(self.current_shape.pointslist) == 2 else None)
                    corner = self._clamp_rectangle_corner(first, end_point, previous)
                    self.current_shape.pointslist = [first, corner]
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
                        # 添加第二个点，完成第一条边的创建
                        self.current_shape.pointslist.append(
                            self._clamp_rotated_first_edge(start_point, pos))
                        self.rotated_rect_stage = 2  # 进入第二阶段
                        self.drawing = True
                        self.update()  # 立即更新显示


        elif self.mode == 'edit':
            if self._finish_geometry_edit():
                self.shapesChanged.emit()
                # Preview already painted old/new geometry; only finish this region.
                region = QtCore.QRectF()
                for shape in self.selected_shape:
                    region = region.united(shape.visual_bounds(
                        scale=None if display.current.auto_scale else self.scale_factor))
                if not region.isEmpty():
                    self.update(region)
        super(Canvas, self).mouseReleaseEvent(event)

###############################################
############ 关于鼠标事件代码===========DoubleClick
###############################################
    def mouseDoubleClickEvent(self, event):
        """处理双击事件"""
        if self.mode == 'create' and self.create_shape_type == 'polygon':
            if self.drawing:
                self.finish_shape()
