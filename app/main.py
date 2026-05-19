from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import agent, audio, audio_tts, dashboard, devices, health
from app.api._errors import register_exception_handlers
from app.config import settings
from app.scheduler.lifecycle import start_scheduler, stop_scheduler


@asynccontextmanager
async def lifespan(app: FastAPI):
    """FastAPI lifespan: start the Reminder Scheduler on startup (gated by
    ``settings.scheduler_enabled``) and shut it down on application
    shutdown.

    The scheduler instance is stored on ``app.state.scheduler`` so
    ``stop_scheduler`` (and any other shutdown logic) can locate it. When
    ``settings.scheduler_enabled`` is ``False`` no scheduler is created
    and ``app.state.scheduler`` is left as ``None``.
    """
    if settings.scheduler_enabled:
        app.state.scheduler = start_scheduler(app)
    else:
        app.state.scheduler = None
    try:
        yield
    finally:
        stop_scheduler(app)


app = FastAPI(
    title="Taskbot Backend",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def add_protocol_version_header(request, call_next):
    response = await call_next(request)
    if request.url.path.startswith("/agent/audio"):
        response.headers["X-Lyla-Protocol"] = "1"
    return response

# Register global Service Layer exception handlers (Req 12.7, 13.6, 13.7).
# Done before including routers so every endpoint inherits the mapping
# from NotFoundError/ValidationError/PermissionDeniedError to
# HTTP 404/422/403 with a uniform ``{"detail": "..."}`` body.
register_exception_handlers(app)

app.include_router(health.router, tags=["Health"])
app.include_router(agent.router)
app.include_router(audio.router)
app.include_router(audio_tts.router)
app.include_router(devices.router)
app.include_router(dashboard.router)
