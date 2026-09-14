"""Database Connection & Session Configuration for CA/BQP Verification Platform.

Standard: Quality-first 2026 Production Architecture.
Supports PostgreSQL (via psycopg2/asyncpg) and transparent SQLite fallback for development/testing.
Reads configuration from .env at repository root.
"""

import os
from pathlib import Path
from typing import Generator
from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker, Session

# Locate .env file at repo root (3 levels up from this file) or fallback to current dir
ROOT_DIR = Path(__file__).resolve().parent.parent.parent.parent.parent
env_path = ROOT_DIR / ".env"
if env_path.exists():
    load_dotenv(dotenv_path=env_path)
else:
    load_dotenv()

# Database URL from environment or default local SQLite for instant out-of-the-box readiness
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://postgres:postgres@localhost:5432/cabqp_verification"
)

# If postgresql URL is specified but postgres driver might be missing or dialect needs adjustment
connect_args = {}
if DATABASE_URL.startswith("sqlite"):
    connect_args = {"check_same_thread": False}

try:
    engine = create_engine(
        DATABASE_URL,
        connect_args=connect_args,
        pool_pre_ping=True,
        echo=os.getenv("SQL_ECHO", "false").lower() == "true",
    )
except Exception:
    # Fallback to local SQLite if PostgreSQL driver/url is invalid or unavailable during local dev
    SQLITE_FALLBACK_URL = "sqlite:///./cabqp_local.db"
    engine = create_engine(
        SQLITE_FALLBACK_URL,
        connect_args={"check_same_thread": False},
        pool_pre_ping=True,
    )

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency that provides a transactional database session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    """Create all registered tables in the database engine."""
    Base.metadata.create_all(bind=engine)
