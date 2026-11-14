from fastapi import APIRouter

router = APIRouter()


@router.get("/health", tags=["health"])
def health() -> dict[str, str]:
    """Liveness only; database connectivity is checked separately."""
    return {"status": "ok"}
