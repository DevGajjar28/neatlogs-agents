from pathlib import Path

content = """\"\"\"Local JSON API for SignalSDR UI. Bind 127.0.0.1 only.\"\"\"

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import campaigns, system
from app.config import get_settings
from app.infra.db import init_db

app = FastAPI(title=\"SignalSDR API\", version=\"0.1.0\")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[\"http://localhost:3000\"],
    allow_credentials=True,
    allow_methods=[\"*\"],
    allow_headers=[\"*\"],
)
app.include_router(system.router, prefix=\"/api\"))
app.include_router(campaigns.router, prefix=\"/api\"))


@app.on_event(\"startup\")
def _startup() -> None:
    init_db(get_settings().db_path)
"""

Path("app/api/main.py").write_text(content, encoding="utf-8")
print(Path("app/api/main.py").read_text(encoding="utf-8"))
