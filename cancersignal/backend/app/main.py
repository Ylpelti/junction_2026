"""CancerSignal public API; synthetic-data demonstration only."""

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from app.api.health import router as health_router
from app.api.router import router as api_router
from app.services.errors import ServiceError

app = FastAPI(
    title="CancerSignal API",
    description="Junction 2026 hackathon prototype. Synthetic patient data only.",
    version="0.1.0",
)

app.include_router(health_router)
app.include_router(api_router)
app.add_middleware(CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_methods=["GET", "POST"], allow_headers=["Content-Type"])


@app.exception_handler(ServiceError)
async def service_error(request: Request, error: ServiceError):
    return JSONResponse(status_code=error.status_code, content={"detail": error.detail})


@app.exception_handler(IntegrityError)
async def integrity_error(request: Request, error: IntegrityError):
    return JSONResponse(status_code=409, content={"detail": "Record conflicts with an existing ID or database constraint."})


@app.exception_handler(SQLAlchemyError)
async def database_error(request: Request, error: SQLAlchemyError):
    return JSONResponse(status_code=503, content={"detail": "Database operation unavailable."})
