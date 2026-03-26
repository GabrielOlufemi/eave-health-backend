"""
init_db.py — Run this once to create all tables in Neon.

Usage:
    python -m app.init_db

It reads DATABASE_URL_SYNC from .env and executes createeave-updated.sql.
"""

import os
from pathlib import Path
from dotenv import load_dotenv
import sqlalchemy

load_dotenv()

SYNC_URL = os.environ.get(
    "DATABASE_URL_SYNC",
    os.environ["DATABASE_URL"].replace("+asyncpg", ""),
)


def init():
    print(f"[init_db] Connecting to: {SYNC_URL[:60]}...")
    engine = sqlalchemy.create_engine(SYNC_URL)

    sql_file = Path(__file__).parent.parent / "createeave-updated.sql"
    if not sql_file.exists():
        # Try using ORM metadata instead
        print("[init_db] SQL file not found — creating tables from ORM models...")
        from app.db.models import Base
        Base.metadata.create_all(engine)
        print("[init_db] Tables created from ORM.")
        return

    sql = sql_file.read_text()
    # Run each statement in its own transaction so one failure doesn't block the rest
    for stmt in sql.split(";"):
        stmt = stmt.strip()
        if not stmt or stmt.startswith("--"):
            continue
        # Skip pure comment blocks
        lines = [l.strip() for l in stmt.splitlines() if l.strip() and not l.strip().startswith("--")]
        if not lines:
            continue
        try:
            with engine.begin() as conn:
                conn.execute(sqlalchemy.text(stmt))
        except Exception as e:
            if "already exists" in str(e):
                continue
            print(f"[init_db] Warning: {e}")

    print("[init_db] All tables and indexes created successfully.")


if __name__ == "__main__":
    init()