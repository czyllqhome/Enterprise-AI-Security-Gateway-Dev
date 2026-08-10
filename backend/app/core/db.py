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
    engine = create_engine(resolved_url)
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
