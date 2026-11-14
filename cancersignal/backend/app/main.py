"""Minimal FastAPI entry point; clinical features are not implemented yet."""

from fastapi import FastAPI

app = FastAPI(
    title="CancerSignal API",
    description="Junction 2026 hackathon prototype. Synthetic patient data only.",
    version="0.1.0",
)


@app.get("/health", tags=["health"])
def health() -> dict[str, str]:
    return {"status": "ok"}
