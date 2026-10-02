"""Writable output paths for a Finder-launched macOS app bundle."""

import os
import sys
from pathlib import Path


def macos_output_dir(name):
    """Keep source-run defaults; avoid writing into an .app or Finder's cwd."""
    executable = Path(sys.executable)
    in_bundle = any(part.lower().endswith('.app') for part in executable.parts)
    if not (getattr(sys, 'frozen', False) or in_bundle):
        return os.path.join(os.getcwd(), name)
    from PyQt5.QtCore import QStandardPaths

    documents = QStandardPaths.writableLocation(QStandardPaths.DocumentsLocation)
    return str(Path(documents or Path.home()) / 'StomataQuant' / name)


def macos_resource_path(name):
    """Find an optional file shipped in a macOS .app or beside the source."""
    if Path(name).name != name:
        raise ValueError('Resource name must be a file name.')
    executable = Path(sys.executable)
    bundle = next((parent for parent in executable.parents
                   if parent.name.lower().endswith('.app')), None)
    locations = []
    if bundle is not None:
        locations.append(bundle / 'Contents' / 'Resources')
    extracted = getattr(sys, '_MEIPASS', None)
    if extracted:
        locations.append(Path(extracted))
    locations.append(Path(__file__).resolve().parent)
    return next((str(base / name) for base in locations if (base / name).is_file()), None)
