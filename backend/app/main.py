"""FastAPI application entry point."""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import get_settings
from app.routers import auth_router, health_router, itineraries_router, profile_router, trips_router, voice_router
from app.utils.errors import TravelPlanningError
from app.utils.logging import configure_logging, get_logger
from app.utils.tracing import generate_trace_id, set_trace_id

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    configure_logging(settings.log_level)
    logger.info("Application starting", extra={"event": {"app_env": settings.app_env}})
    yield
    logger.info("Application shutdown", extra={"event": {"app_env": settings.app_env}})


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="Travel Planning Multi-Agent API",
        version="0.1.0",
        lifespan=lifespan,
    )

    origins = settings.cors_origins
    if isinstance(origins, str):
        origins = [o.strip() for o in origins.split(",") if o.strip()]

    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.middleware("http")
    async def trace_middleware(request: Request, call_next):
        incoming = request.headers.get("X-Trace-Id")
        trace_id = incoming or generate_trace_id()
        set_trace_id(trace_id)
        response = await call_next(request)
        response.headers["X-Trace-Id"] = trace_id
        return response

    @app.get("/", tags=["metadata"])
    async def root():
        """Root API metadata endpoint."""
        return {
            "status": "ok",
            "service": "Travel Planning Multi-Agent API",
            "version": "0.1.0",
            "documentation": "/docs"
        }

    # Include routers
    app.include_router(health_router)
    app.include_router(auth_router)
    app.include_router(trips_router)
    app.include_router(itineraries_router)
    app.include_router(profile_router)
    app.include_router(voice_router)

    @app.exception_handler(TravelPlanningError)
    async def travel_error_handler(_request: Request, exc: TravelPlanningError):
        return JSONResponse(status_code=400, content=exc.to_dict())

    return app


app = create_app()
