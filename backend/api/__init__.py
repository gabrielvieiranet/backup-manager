# backend/api/__init__.py
from fastapi import APIRouter

from .auth import router as auth_router
from .execution import router as execution_router
from .jobs import router as jobs_router

api_router = APIRouter()

api_router.include_router(auth_router)
api_router.include_router(jobs_router)
api_router.include_router(execution_router)
