"""Vercel FastAPI entrypoint. Also run locally with `uvicorn app:app`."""

import sys
from pathlib import Path

root = Path(__file__).resolve().parent
sys.path.insert(0, str(root / "backend"))

from lists_api.web import create_web_app  # noqa: E402

app = create_web_app()
