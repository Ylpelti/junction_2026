"""Run with `python -m app.db.check` to verify PostgreSQL and pgvector."""

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.db.session import get_engine


def main() -> None:
    engine = get_engine()
    try:
        with engine.connect() as connection:
            if connection.scalar(text("SELECT 1")) != 1:
                raise SystemExit("Database check failed: unexpected SELECT 1 result.")
            version = connection.scalar(
                text("SELECT extversion FROM pg_extension WHERE extname = 'vector'")
            )
            if version is None:
                raise SystemExit("Database connected, but the vector extension is not enabled.")
    except SQLAlchemyError:
        # Do not print connection strings or driver errors containing credentials.
        raise SystemExit("Database connection failed. Check .env and docker compose ps.") from None
    finally:
        engine.dispose()
    print(f"Database connection OK; pgvector {version} enabled.")


if __name__ == "__main__":
    main()
