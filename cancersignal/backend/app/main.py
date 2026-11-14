"""CancerSignal public API; synthetic-data demonstration only."""

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from app.api.health import router as health_router
from app.api.router import router as api_router
from app.core.config import WebSettings, get_web_settings
from app.services.errors import ServiceError

async def service_error(request: Request, error: ServiceError):
    return JSONResponse(status_code=error.status_code, content={"detail": error.detail})


async def integrity_error(request: Request, error: IntegrityError):
    return JSONResponse(status_code=409, content={"detail": "Record conflicts with an existing ID or database constraint."})


async def database_error(request: Request, error: SQLAlchemyError):
    return JSONResponse(status_code=503, content={"detail": "Database operation unavailable."})


def create_app(web_settings: WebSettings | None = None) -> FastAPI:
    settings = web_settings if web_settings is not None else get_web_settings()
    application = FastAPI(
        title="CancerSignal API",
        description="Junction 2026 hackathon prototype. Synthetic patient data only.",
        version="0.1.0",
    )
    application.include_router(health_router)
    application.include_router(api_router)
    application.add_middleware(CORSMiddleware,
        allow_origins=settings.cors_origins, allow_credentials=False,
        allow_methods=["GET", "POST"], allow_headers=["Content-Type"], max_age=600)
    application.add_exception_handler(ServiceError, service_error)
    application.add_exception_handler(IntegrityError, integrity_error)
    application.add_exception_handler(SQLAlchemyError, database_error)
    return application


app = create_app()
