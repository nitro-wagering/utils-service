from fastapi import APIRouter

from nitro_utils.api.bets import router as bets_router
from nitro_utils.api.watchlist import router as watchlist_router

api_router = APIRouter(prefix="/api")
api_router.include_router(watchlist_router)
api_router.include_router(bets_router)
