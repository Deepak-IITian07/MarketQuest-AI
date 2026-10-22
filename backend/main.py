from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import health, market
from app.core.config import get_settings

settings = get_settings()
origins = settings.cors_origins if isinstance(settings.cors_origins, list) else [settings.cors_origins]

app = FastAPI(title="MarketQuest AI API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(market.router)
