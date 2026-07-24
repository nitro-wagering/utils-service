from fastapi import APIRouter

from nitro_utils.api.watchlist import router as watchlist_router

api_router = APIRouter(prefix="/api")
api_router.include_router(watchlist_router)
