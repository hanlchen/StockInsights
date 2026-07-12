from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

from app.config import settings

is_sqlite = settings.database_url.startswith("sqlite")
connect_args = {"check_same_thread": False} if is_sqlite else {}

# pool_pre_ping matters once DATABASE_URL points at Supabase (or any managed
# Postgres) instead of local SQLite: Supabase's connection pooler (and most
# managed Postgres providers) silently drops idle connections after a while,
# and a free-tier Render backend that spins down between requests will hit
# exactly that -- without pre_ping, the first request after a gap fails with
# a raw "server closed the connection unexpectedly" instead of SQLAlchemy
# transparently reconnecting. No-op / harmless for SQLite.
engine = create_engine(settings.database_url, connect_args=connect_args, pool_pre_ping=not is_sqlite)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def get_db():
    """FastAPI dependency: yields a DB session, closes it after the request."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
