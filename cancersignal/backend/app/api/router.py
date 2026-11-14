from fastapi import APIRouter

from app.api.routes import analyses, encounters, observations, patients

router = APIRouter(prefix="/api/v1")
for routes in (patients, encounters, observations, analyses):
    router.include_router(routes.router)
