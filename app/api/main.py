"""Local JSON API for SignalSDR UI. Bind 127.0.0.1 only."""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import campaigns, mail, system
from app.config import get_settings
from app.infra.db import init_db


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db(get_settings().db_path)
    yield


app = FastAPI(title="SignalSDR API", version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(system.router, prefix="/api")
app.include_router(campaigns.router, prefix="/api")
app.include_router(mail.router, prefix="/api")
