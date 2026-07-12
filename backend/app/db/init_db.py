"""Creates all tables. Run once at startup (see app/main.py) and optionally
standalone: `python -m app.db.init_db`."""

from app.db import models  # noqa: F401  (ensures models are registered on Base)
from app.db.session import Base, engine


def init_db() -> None:
    Base.metadata.create_all(bind=engine)


if __name__ == "__main__":
    init_db()
    print("Database tables created.")
