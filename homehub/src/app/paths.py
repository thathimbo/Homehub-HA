"""Where HomeHub keeps its files.

Each folder defaults to one next to the code, as before. The Home Assistant add-on points
them at its persistent storage with the HOMEHUB_*_DIR environment variables.
"""
import os

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))


def _folder(env_name: str, default_name: str) -> str:
    return os.path.abspath(os.environ.get(env_name) or os.path.join(BASE_DIR, default_name))


DATA_DIR = _folder('HOMEHUB_DATA_DIR', 'data')
UPLOADS_DIR = _folder('HOMEHUB_UPLOADS_DIR', 'uploads')
MEDIA_DIR = _folder('HOMEHUB_MEDIA_DIR', 'media')
PDFS_DIR = _folder('HOMEHUB_PDFS_DIR', 'pdfs')
