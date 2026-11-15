from fastapi import APIRouter

router = APIRouter()


@router.get("/health", tags=["health"])
def health() -> dict[str, str]:
    """Liveness only; database connectivity is checked separately."""
    return {"status": "ok"}


@router.get("/ready", tags=["health"])
def ready():
    """Database, extension and migration readiness; never return connection details."""
    from pathlib import Path
    from alembic.config import Config
    from alembic.runtime.migration import MigrationContext
    from alembic.script import ScriptDirectory
    from fastapi.responses import JSONResponse
    from sqlalchemy import text
    from app.db.session import get_engine

    try:
        config = Config()
        config.set_main_option("script_location", str(Path(__file__).resolve().parents[2] / "alembic"))
        expected = set(ScriptDirectory.from_config(config).get_heads())
        with get_engine().connect() as connection:
            current = set(MigrationContext.configure(connection).get_current_heads())
            vector = connection.scalar(text("SELECT EXISTS (SELECT 1 FROM pg_extension WHERE extname='vector')"))
        if len(expected) != 1 or current != expected or not vector:
            raise RuntimeError("Database not ready")
    except Exception:
        return JSONResponse(status_code=503, content={"status": "unavailable"})
    return {"status": "ready"}
