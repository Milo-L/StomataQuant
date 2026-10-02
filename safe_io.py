"""Atomic output writes and source-specific names for generated files."""
import hashlib
import os
import tempfile
from pathlib import Path


def source_suffix(source_path):
    source = os.path.normcase(os.path.abspath(os.fspath(source_path)))
    return hashlib.sha256(source.encode('utf-8')).hexdigest()[:16]


def source_basename(source_path):
    return f'{Path(source_path).stem}__{source_suffix(source_path)}'


def available_output_path(directory, filename, source_path=None):
    """Keep the familiar name when free; never select an existing output."""
    directory = Path(directory)
    candidate = directory / filename
    if not candidate.exists():
        return candidate
    stem, ext = os.path.splitext(filename)
    suffix = '__' + source_suffix(source_path or filename)
    if not stem.endswith(suffix):
        stem += suffix
    candidate = directory / (stem + ext)
    number = 2
    while candidate.exists():
        candidate = directory / f'{stem}_{number}{ext}'
        number += 1
    return candidate


def write_bytes_atomic(path, data, *, overwrite=True):
    path = Path(path)
    # Keep the temporary file beside the destination for atomic replacement,
    # without repeating a potentially near-MAX_PATH destination name.
    fd, temporary = tempfile.mkstemp(prefix='.sq-', suffix='.tmp', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as stream:
            if stream.write(data) != len(data):
                raise OSError('Incomplete output write.')
            stream.flush()
            os.fsync(stream.fileno())
        if overwrite:
            os.replace(temporary, path)
        else:
            # Windows rename and POSIX link both fail if a competing writer won.
            if os.name == 'nt':
                os.rename(temporary, path)
            else:
                os.link(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def write_text_atomic(path, data, *, overwrite=True, encoding='utf-8'):
    write_bytes_atomic(path, data.encode(encoding), overwrite=overwrite)


def write_unique_text_atomic(directory, filename, source_path, data):
    """Publish without replacing a concurrent writer's output."""
    while True:
        path = available_output_path(directory, filename, source_path)
        try:
            write_text_atomic(path, data, overwrite=False)
            return path
        except FileExistsError:
            continue
