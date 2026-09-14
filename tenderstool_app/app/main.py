from __future__ import annotations

import asyncio
import sys
import warnings
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from .routes import router

if sys.platform == "win32":
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", category=DeprecationWarning, message=".*WindowsProactorEventLoopPolicy.*")
        warnings.filterwarnings("ignore", category=DeprecationWarning, message=".*asyncio.set_event_loop_policy.*")
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

app = FastAPI(title="TendersTool Automation")
app.include_router(router)
app.mount(
    "/static",
    StaticFiles(directory=str(Path(__file__).resolve().parent / "static")),
    name="static",
)
