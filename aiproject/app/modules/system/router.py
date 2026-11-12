from fastapi import APIRouter

from app.core.database import ping_database

router = APIRouter(tags=["system"])


@router.get("/health")
def health():
    return {"status": "ok"}


@router.get("/health/db")
def health_db():
    if ping_database():
        return {"status": "ok", "database": "connected"}
    return {"status": "degraded", "database": "unavailable"}
