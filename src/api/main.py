from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator

import structlog
from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from src.api.routers import config, schedules, ws
from src.domain.exceptions import DomainError, ScheduleNotFoundError
from src.infrastructure.config.settings import settings
from src.infrastructure.persistence.database import Base, engine

structlog.configure(
    processors=[
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.stdlib.add_log_level,
        structlog.processors.JSONRenderer(),
    ],
    wrapper_class=structlog.BoundLogger,
    logger_factory=structlog.PrintLoggerFactory(),
)

logger = structlog.get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Run DB migrations / table creation on startup."""
    logger.info("Starting up Class Scheduling Engine")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("Database tables ready")
    yield
    logger.info("Shutting down")


app = FastAPI(
    title="Class Scheduling Engine",
    description=(
        "Automatic academic timetable generation based on the Esquivel Tovar (2014) "
        "mathematical model. Supports multi-campus scheduling with PROCOM, PROJEX, "
        "and PROHES teacher types."
    ),
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
)

# ── CORS ──────────────────────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Routers ───────────────────────────────────────────────────────────────────
app.include_router(schedules.router)
app.include_router(config.router)
app.include_router(ws.router)


# ── Global exception handlers ────────────────────────────────────────────────
@app.exception_handler(DomainError)
async def domain_error_handler(request: Request, exc: DomainError) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={"detail": str(exc), "type": "DomainError"},
    )


@app.exception_handler(ScheduleNotFoundError)
async def not_found_handler(request: Request, exc: ScheduleNotFoundError) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_404_NOT_FOUND,
        content={"detail": str(exc), "type": "ScheduleNotFoundError"},
    )


@app.exception_handler(ValueError)
async def value_error_handler(request: Request, exc: ValueError) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_400_BAD_REQUEST,
        content={"detail": str(exc), "type": "ValueError"},
    )


# ── Health check ──────────────────────────────────────────────────────────────
@app.get("/health", tags=["Health"], summary="Health check")
async def health() -> dict[str, str]:
    return {"status": "ok", "service": "class-scheduling-engine"}
