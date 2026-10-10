from pathlib import Path
import traceback

# Build without nested quote traps
parts = []
parts.append('"""Local JSON API for SignalSDR UI. Bind 127.0.0.1 only."""\n')
parts.append("from __future__ import annotations\n\n")
parts.append("from fastapi import FastAPI\n")
parts.append("from fastapi.middleware.cors import CORSMiddleware\n\n")
parts.append("from app.api.routes import campaigns, system\n")
parts.append("from app.config import get_settings\n")
parts.append("from app.infra.db import init_db\n\n")
parts.append("app = FastAPI(title='SignalSDR API', version='0.1.0')\n")
parts.append("app.add_middleware(\n")
parts.append("    CORSMiddleware,\n")
parts.append("    allow_origins=['http://localhost:3000'],\n")
parts.append("    allow_credentials=True,\n")
parts.append("    allow_methods=['*'],\n")
parts.append("    allow_headers=['*'],\n")
parts.append(")\n")
parts.append("app.include_router(system.router, prefix='/api')\n")
parts.append("app.include_router(campaigns.router, prefix='/api')\n\n\n")
parts.append("@app.on_event('startup')\n")
parts.append("def _startup() -> None:\n")
parts.append("    init_db(get_settings().db_path)\n")
src = "".join(parts)
Path("app/api/main.py").write_text(src, encoding="utf-8")
print(src)
try:
    compile(src, "app/api/main.py", "exec")
    print("COMPILE OK")
except SyntaxError:
    traceback.print_exc()
