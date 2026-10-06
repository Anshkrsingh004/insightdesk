"""FastAPI app = the Section 6 contract. Phase 0 wires /health + all endpoint
shapes; the /support pipeline is filled in Phase 2+.
"""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI

from .api.routes import router
from .db import init_db


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()  # ensure Annex C schema exists
    yield


app = FastAPI(
    title="InsightDesk",
    description="Self-serve customer support with safe escalation (HCL Hackathon UC2).",
    version="0.1.0",
    lifespan=lifespan,
)
app.include_router(router)


@app.get("/")
def root() -> dict:
    return {"service": "InsightDesk", "docs": "/docs", "health": "/health"}
