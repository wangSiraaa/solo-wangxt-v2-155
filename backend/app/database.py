from functools import lru_cache
from os import environ

from pydantic_settings import BaseSettings
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker


class Settings(BaseSettings):
    database_url: str = "sqlite+pysqlite:///./bridge.db"
    cors_origin: str = "http://localhost:5173"


@lru_cache
def get_settings() -> Settings:
    return Settings()


class Base(DeclarativeBase):
    pass


def _database_url() -> str:
    # Docker Compose commonly passes POSTGRES_*; allow the app to run without
    # an explicit DATABASE_URL in development as well.
    if environ.get("DATABASE_URL"):
        return environ["DATABASE_URL"]
    host = environ.get("POSTGRES_HOST")
    if host:
        user = environ.get("POSTGRES_USER", "bridge")
        password = environ.get("POSTGRES_PASSWORD", "bridge")
        db = environ.get("POSTGRES_DB", "bridge")
        port = environ.get("POSTGRES_PORT", "5432")
        return f"postgresql+psycopg://{user}:{password}@{host}:{port}/{db}"
    return get_settings().database_url


engine = create_engine(_database_url(), pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
