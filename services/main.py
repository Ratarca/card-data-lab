"""FastAPI modular monolith entrypoint.

Each bounded context is a module router under services/modules/.
"""
from __future__ import annotations

from fastapi import FastAPI

from services.modules.authorization.router import router as authorization_router

app = FastAPI(title="card-data-lab", version="0.1.0")

app.include_router(authorization_router, prefix="/api")


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}
