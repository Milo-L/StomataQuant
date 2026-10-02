"""Process boundary for model backends that may ignore thread interruption."""
import json
import os
import sys
from pathlib import Path


def main(config_path, response_path):
    response = {}
    try:
        from ultralytics import YOLO

        config = json.loads(Path(config_path).read_text(encoding='utf-8'))
        model = YOLO(config['model_path'])
        if config['kind'] == 'classification':
            probabilities = [0.0, 0.0]
            for result in model.predict(config['file_path'], device='cpu'):
                probs = result.probs.data.cpu().numpy()
                probabilities = [float(probs[0] * 100), float(probs[1] * 100)]
            response['probabilities'] = probabilities
        else:
            predictions = model.predict(**config['params'])
            response['predictions'] = [dict(path=str(result.path), json=result.to_json())
                                       for result in predictions]
    except Exception as error:
        response['error'] = str(error)
    Path(response_path).write_text(json.dumps(response, ensure_ascii=False), encoding='utf-8')


def batch_main(model_path):
    """Serve one Batch with one model, keeping the existing prediction contract."""
    from ultralytics import YOLO

    model = YOLO(model_path)
    for line in sys.stdin:
        try:
            job = json.loads(line)
            request_path = Path(job['request'])
            response_path = Path(job['response'])
            response = {}
            try:
                config = json.loads(request_path.read_text(encoding='utf-8'))
                if config['model_path'] != model_path or config['kind'] != 'segmentation':
                    raise ValueError('Batch model changed during inference.')
                predictions = model.predict(**config['params'])
                response['predictions'] = [dict(path=str(result.path), json=result.to_json())
                                           for result in predictions]
                del predictions
            except Exception as error:
                response['error'] = str(error)
            temporary_response = response_path.with_suffix('.tmp')
            temporary_response.write_text(json.dumps(response, ensure_ascii=False), encoding='utf-8')
            os.replace(temporary_response, response_path)
        except Exception:
            # A malformed request has no trusted response path. Stop the session.
            break


if __name__ == '__main__':
    if len(sys.argv) == 3 and sys.argv[1] == '--batch':
        batch_main(sys.argv[2])
    else:
        main(sys.argv[1], sys.argv[2])
