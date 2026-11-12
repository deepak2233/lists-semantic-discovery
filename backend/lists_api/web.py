"""Same-origin inference playground and public, fixed-corpus demo deployment."""

import os
import re
from dataclasses import replace
from pathlib import Path

from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .config import Settings
from .main import create_app

ROOT = Path(__file__).resolve().parents[2]
PUBLIC = ROOT / "public"


def web_settings() -> Settings:
    settings = Settings.from_env()
    hosts, origins = list(settings.allowed_hosts), list(settings.web_origins)
    for name in ("VERCEL_URL", "VERCEL_PROJECT_PRODUCTION_URL", "LISTS_PUBLIC_HOST"):
        host = os.getenv(name, "").lower()
        if host:
            if not re.fullmatch(r"[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?", host) or ".." in host:
                raise ValueError(f"Invalid deployment hostname in {name}")
            hosts.append(host)
            origins.append("https://" + host)
    # Development origins are exact, with explicit ports. No wildcard CORS or trusted hosts.
    if not os.getenv("VERCEL"):
        origins.extend(["http://127.0.0.1:8000", "http://localhost:8000"])
    manifest = ROOT / "models/minilm/manifest.json"
    return replace(
        settings,
        environment=os.getenv("LISTS_ENV", "demo"),
        allowed_hosts=tuple(dict.fromkeys(hosts)),
        web_origins=tuple(dict.fromkeys(origins)),
        semantic_model_path=settings.semantic_model_path
        or (str(manifest.parent) if manifest.is_file() else ""),
    )


def create_web_app(settings: Settings | None = None):
    app = create_app(settings or web_settings())

    @app.get("/", include_in_schema=False)
    async def home():
        return FileResponse(PUBLIC / "index.html", media_type="text/html")

    @app.get("/favicon.svg", include_in_schema=False)
    async def favicon():
        return FileResponse(PUBLIC / "favicon.svg", media_type="image/svg+xml")

    # In Vercel, public/assets is served directly by its CDN. Mount only for local development.
    if not os.getenv("VERCEL"):
        app.mount("/assets", StaticFiles(directory=PUBLIC / "assets"), name="playground-assets")
    return app
