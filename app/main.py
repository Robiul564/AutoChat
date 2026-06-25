from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from starlette.middleware.trustedhost import TrustedHostMiddleware

from app.api.routes import analytics, businesses, conversations, knowledge, onboarding, platform, settings, tools, webhooks, whatsapp
from app import models  # noqa: F401 - register ORM tables before create_all()
from app.core.config import settings as app_settings
from app.core.db import Base, SessionLocal, engine, ensure_runtime_schema
from app.core.middleware import RequestContextMiddleware
from app.services.tools import seed_tools
from app.workers.queue import event_queue


@asynccontextmanager
async def lifespan(app: FastAPI):
    app_settings.validate_for_runtime()
    Base.metadata.create_all(bind=engine)
    ensure_runtime_schema()
    db = SessionLocal()
    try:
        seed_tools(db)
    finally:
        db.close()
    await event_queue.start()
    yield
    await event_queue.stop()


app = FastAPI(
    title=app_settings.app_name,
    version="0.1.0",
    lifespan=lifespan,
    docs_url="/docs" if app_settings.enable_docs else None,
    redoc_url="/redoc" if app_settings.enable_docs else None,
    openapi_url="/openapi.json" if app_settings.enable_docs else None,
)
app.add_middleware(RequestContextMiddleware)
app.add_middleware(TrustedHostMiddleware, allowed_hosts=app_settings.allowed_host_list)
app.add_middleware(
    CORSMiddleware,
    allow_origins=app_settings.allowed_origin_list,
    allow_methods=["*"],
    allow_headers=["Content-Type", "X-User-Email", "X-Admin-Key", "X-Hub-Signature-256", "X-Request-ID"],
)

app.include_router(businesses.router)
app.include_router(whatsapp.router)
app.include_router(webhooks.router)
app.include_router(knowledge.router)
app.include_router(onboarding.router)
app.include_router(conversations.router)
app.include_router(tools.router)
app.include_router(settings.router)
app.include_router(analytics.router)
app.include_router(platform.router)


@app.get("/api/health", tags=["platform"])
def health():
    return {"ok": True}


app.mount("/", StaticFiles(directory="app/static", html=True), name="static")
