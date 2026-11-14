from fastapi import APIRouter

from app.api.routes import analyses, encounters, observations, patients, reviews

router = APIRouter(prefix="/api/v1")
for routes in (patients, encounters, observations, analyses, reviews):
    router.include_router(routes.router)
