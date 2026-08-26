from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import inspect, text

from .api.routes_admin_users import router as admin_users_router
from .api.routes_auth import router as auth_router
from .api.routes_chat import router as chat_router
from .api.routes_console import router as console_router
from .api.routes_file_review import router as file_review_router
from .api.routes_health import router as health_router
from .api.routes_logs import router as logs_router
from .api.routes_providers import router as providers_router
from .api.routes_sessions import router as sessions_router
from .core.config import get_settings
from .core.db import Base, SessionLocal, configure_database
from .core.logging import configure_logging
from .models import ChatLog, ChatMessage, ChatSession, ProviderCredential, ScanEvent, SystemSetting, UploadedFile, User  # noqa: F401
from .services.auth_service import ensure_default_admin
from .services.guardrails.llm_guard_service import get_guardrail_service
from .workers.file_review_worker import FileReviewWorker


def ensure_schema_compatibility(engine) -> None:
    inspector = inspect(engine)
    table_names = inspector.get_table_names()
    if "chat_sessions" not in table_names:
        return

    column_names = {column["name"] for column in inspector.get_columns("chat_sessions")}
    if "created_by" not in column_names:
        with engine.begin() as connection:
            connection.execute(
                text("ALTER TABLE chat_sessions ADD COLUMN created_by VARCHAR(128) NOT NULL DEFAULT 'Guest'"),
            )

    if "scan_events" in table_names:
        scan_event_column_names = {column["name"] for column in inspector.get_columns("scan_events")}
        if "business_sensitive_result_json" not in scan_event_column_names:
            with engine.begin() as connection:
                connection.execute(
                    text("ALTER TABLE scan_events ADD COLUMN business_sensitive_result_json JSON"),
                )
        if "privacy_filter_hit_count" not in scan_event_column_names:
            with engine.begin() as connection:
                connection.execute(
                    text("ALTER TABLE scan_events ADD COLUMN privacy_filter_hit_count INTEGER NOT NULL DEFAULT 0"),
                )


@asynccontextmanager
async def lifespan(_: FastAPI):
    configure_logging()
    engine = configure_database()
    Base.metadata.create_all(bind=engine)
    ensure_schema_compatibility(engine)
    db = SessionLocal()
    file_review_worker: FileReviewWorker | None = None
    try:
        ensure_default_admin(db)
        # Model loading and real scanner warmups happen before readiness can pass,
        # so the first user request never pays the cold-start cost.
        get_guardrail_service()
        if get_settings().file_review_worker_mode.strip().lower() == "embedded":
            file_review_worker = FileReviewWorker()
            file_review_worker.start()
    finally:
        db.close()
    try:
        yield
    finally:
        if file_review_worker is not None:
            file_review_worker.stop()


app = FastAPI(title="Enterprise AI Security Gateway API", lifespan=lifespan)
settings = get_settings()
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(health_router)
app.include_router(auth_router)
app.include_router(admin_users_router)
app.include_router(sessions_router)
app.include_router(chat_router)
app.include_router(console_router)
app.include_router(file_review_router)
app.include_router(logs_router)
app.include_router(providers_router)


@app.get("/", include_in_schema=False)
async def api_root() -> JSONResponse:
    return JSONResponse(
        {
            "service": "Enterprise AI Security Gateway API",
            "status": "ok",
            "frontend": "http://127.0.0.1:5173/login",
            "admin": "http://127.0.0.1:5173/admin",
            "docs": "/docs",
            "health": "/api/health",
        },
        headers={"Cache-Control": "no-store, max-age=0"},
    )
