"""Compatibility router for existing importers. New registration uses domain routers."""
from fastapi import APIRouter
from app.modules.organization.router import router as organization_router
from app.modules.onboarding.router import router as onboarding_router
from app.modules.score.router import router as score_router
from app.modules.feedback.router import router as feedback_router
from app.modules.todo.router import router as todo_router

router = APIRouter()
router.include_router(organization_router)
router.include_router(onboarding_router)
router.include_router(score_router)
router.include_router(feedback_router)
router.include_router(todo_router)
