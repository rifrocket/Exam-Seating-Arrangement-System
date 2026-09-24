from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.exams import router as exams_router
from app.api.health import router as health_router
from app.api.registrations import router as registrations_router
from app.api.rooms import router as rooms_router
from app.api.schedules import router as schedules_router
from app.api.seating import router as seating_router
from app.config import get_settings
from app.db.init_db import init_db


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    # Ensures tables exist on a fresh SQLite file without a separate manual
    # step — safe to call repeatedly, since create_all() is a no-op for
    # tables that already exist.
    init_db()
    yield


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title=settings.app_name, lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(health_router)
    app.include_router(registrations_router)
    app.include_router(schedules_router)
    app.include_router(exams_router)
    app.include_router(rooms_router)
    app.include_router(seating_router)
    return app


app = create_app()
