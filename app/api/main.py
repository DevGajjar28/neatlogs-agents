"""JSON API for SignalSDR UI. Default bind is localhost; EC2 uses API_HOST=0.0.0.0."""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import calendar, campaigns, email_templates, mail, reports, system
from app.config import cors_origin_list, get_settings
from app.infra.db import init_db
from app.infra.email_templates import seed_default_template


@asynccontextmanager
async def lifespan(_app: FastAPI):
    path = get_settings().db_path
    init_db(path)
    seed_default_template(path)
    yield


app = FastAPI(title="SignalSDR API", version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origin_list(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
PREFIX = "/api"
app.include_router(system.router, prefix=PREFIX)
app.include_router(campaigns.router, prefix=PREFIX)
app.include_router(mail.router, prefix=PREFIX)
app.include_router(email_templates.router, prefix=PREFIX)
app.include_router(calendar.router, prefix=PREFIX)
app.include_router(reports.router, prefix=PREFIX)
