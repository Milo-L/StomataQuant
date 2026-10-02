"""Common decoding and shape construction for single-image and batch inference."""
import json
import math
import os
from collections import defaultdict
from PyQt5.QtCore import QPointF
from shape import Shape
from geometry import MIN_POLYGON_VERTICES
from safe_io import write_unique_text_atomic


def decode_predictions(results, output_dir):
    os.makedirs(output_dir, exist_ok=True)
    records = []
    polygons = defaultdict(list)
    for result in results or []:
        items = json.loads(result.to_json())
        if not isinstance(items, list):
            raise ValueError('Prediction JSON must be a list.')
        filename = os.path.splitext(os.path.basename(result.path))[0] + '.json'
        write_unique_text_atomic(output_dir, filename, result.path,
                                 json.dumps(items, indent=4, ensure_ascii=False))
        for item in items:
            classnum = int(item['class'])
            if 'segments' in item:
                xs, ys = item['segments']['x'], item['segments']['y']
                if len(xs) != len(ys) or len(xs) < 3 or not all(math.isfinite(v) for v in xs+ys):
                    raise ValueError('Invalid prediction polygon coordinates.')
                polygons[classnum].append((xs, ys))
            elif 'box' in item:
                if not all(math.isfinite(item['box'][key]) for key in ('x1','y1','x2','y2')):
                    raise ValueError('Invalid prediction box coordinates.')
            else:
                raise ValueError('Prediction has neither a polygon nor a box.')
            records.append(item)
    return records, dict(polygons)


def shapes_from_predictions(records, processed, canvas):
    indices = defaultdict(int)
    counts = defaultdict(int)
    for existing in canvas.shapes:
        if isinstance(existing.group_id, int):
            counts[existing.classnum] = max(counts[existing.classnum], existing.group_id+1)
    shapes = []
    audit = {(entry['classnum'],entry['index']): entry for entry in getattr(processed,'audit',[])}
    for item in records:
        classnum = int(item['class'])
        if 'segments' in item:
            index = indices[classnum]; indices[classnum] += 1
            contour = processed[classnum][index]
            if contour is None:
                continue
            xs, ys = contour
            points = [QPointF(x,y) for x,y in zip(xs,ys)]
            if len({(point.x(), point.y()) for point in points}) < MIN_POLYGON_VERTICES:
                raise ValueError('Prediction polygon requires at least 5 distinct vertices.')
            kind = 'polygon'
        else:
            box = item['box']
            points = [QPointF(box['x1'],box['y1']),QPointF(box['x2'],box['y2'])]
            points[1] = canvas._clamp_rectangle_corner(points[0], points[1])
            kind = 'rectangle'
        shape = Shape(label=item.get('name','undefined'),classnum=classnum,pointslist=points,
                      shape_type=kind,group_id=counts[classnum],scale_factor=canvas.scale_factor)
        counts[classnum] += 1
        if kind == 'polygon':
            shape.polygon_audit = audit.get((classnum,index))
        shapes.append(shape)
    return shapes


def save_polygon_audit(processed, file_path, output_dir):
    audit = getattr(processed,'audit',[])
    if audit:
        filename = os.path.splitext(os.path.basename(file_path))[0] + '.postprocess.json'
        write_unique_text_atomic(output_dir, filename, file_path,
                                 json.dumps(audit, ensure_ascii=False, indent=2))
    return [entry for entry in audit if entry['status']=='rejected']
