from fastapi import APIRouter

from app.api.routes import analyses, encounters, observations, patients, reviews, workflow

router = APIRouter(prefix="/api/v1")
for routes in (patients, encounters, observations, analyses, reviews, workflow):
    router.include_router(routes.router)
