"""Minimal FastAPI entry point; clinical features are not implemented yet."""

from fastapi import FastAPI

from app.api.health import router as health_router

app = FastAPI(
    title="CancerSignal API",
    description="Junction 2026 hackathon prototype. Synthetic patient data only.",
    version="0.1.0",
)

app.include_router(health_router)
