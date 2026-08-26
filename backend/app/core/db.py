from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from .config import get_settings


class Base(DeclarativeBase):
    pass


engine: Engine | None = None
SessionLocal = sessionmaker(autoflush=False, autocommit=False, class_=Session)


def configure_database(database_url: str | None = None) -> Engine:
    global engine

    resolved_url = database_url or get_settings().database_url
    engine_options = {"pool_pre_ping": True}
    if not resolved_url.startswith("sqlite"):
        settings = get_settings()
        engine_options.update(
            {
                "pool_size": max(settings.db_pool_size, 1),
                "max_overflow": max(settings.db_max_overflow, 0),
                "pool_timeout": max(settings.db_pool_timeout_seconds, 1.0),
                "pool_recycle": max(settings.db_pool_recycle_seconds, 60),
            },
        )
    engine = create_engine(resolved_url, **engine_options)
    SessionLocal.configure(bind=engine)
    return engine


def get_engine() -> Engine:
    global engine
    if engine is None:
        engine = configure_database()
    return engine


def get_db() -> Generator[Session, None, None]:
    get_engine()
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
