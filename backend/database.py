import os

from sqlalchemy import create_engine
from sqlalchemy.engine import URL
from sqlalchemy.orm import declarative_base, sessionmaker


def _database_url() -> str:
    configured_url = os.getenv("DATABASE_URL", "").strip()
    if configured_url:
        return configured_url

    required = {
        "DB_HOST": os.getenv("DB_HOST", "").strip(),
        "DB_USER": os.getenv("DB_USER", "").strip(),
        "DB_PASSWORD": os.getenv("DB_PASSWORD", ""),
        "DB_NAME": os.getenv("DB_NAME", "").strip(),
    }
    if any(not value for value in required.values()):
        raise RuntimeError(
            "Configure DATABASE_URL or provide DB_HOST, DB_USER, "
            "DB_PASSWORD and DB_NAME."
        )
    if required["DB_PASSWORD"].lower().startswith(
        ("replace_", "changeme", "change_me")
    ):
        raise RuntimeError("Replace the example database password before startup.")

    return URL.create(
        "postgresql+psycopg",
        username=required["DB_USER"],
        password=required["DB_PASSWORD"],
        host=required["DB_HOST"],
        port=int(os.getenv("DB_PORT", "5432")),
        database=required["DB_NAME"],
    ).render_as_string(hide_password=False)


DATABASE_URL = _database_url()

engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,
)

SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
)

Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
