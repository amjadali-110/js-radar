"""WSGI entry point for gunicorn."""

import sys
from pathlib import Path

# Ensure project root is on sys.path so `backend.*` imports resolve
PROJECT_ROOT = str(Path(__file__).parent.parent)
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from backend.app import create_app

app = create_app()
