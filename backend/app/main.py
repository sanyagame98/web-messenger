from __future__ import annotations

import logging

from fastapi import FastAPI, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app import chat_admin_models, chat_meta_models, profile_meta_models  # noqa: F401 - registers SQLAlchemy metadata
from app.config import settings
from app.database import Base, engine
from app.routers import auth as auth_router
from app.routers import chats as chats_router
from app.routers import files as files_router
from app.routers import messages as messages_router
from app.routers import premium_emoji as premium_emoji_router
from app.routers import roof_tweb_v18 as roof_tweb_router
from app.routers import users as users_router
from app.websocket import websocket_endpoint

logging.basicConfig(level=logging.INFO)

app = FastAPI(title=settings.app_name)


app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def on_startup() -> None:
    Base.metadata.create_all(bind=engine)


app.include_router(auth_router.router, prefix="/api")
app.include_router(users_router.router, prefix="/api")
app.include_router(chats_router.router, prefix="/api")
app.include_router(messages_router.router, prefix="/api")
app.include_router(files_router.router, prefix="/api")
app.include_router(premium_emoji_router.router, prefix="/api")
app.include_router(roof_tweb_router.router, prefix="/api")


app.mount("/uploads", StaticFiles(directory=settings.uploads_dir), name="uploads")


@app.websocket("/ws")
async def ws_route(ws: WebSocket) -> None:
    await websocket_endpoint(ws)


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "network": "roof-only"}


@app.get("/")
def root() -> dict:
    return {"name": settings.app_name, "docs": "/docs", "network": "roof-only"}
