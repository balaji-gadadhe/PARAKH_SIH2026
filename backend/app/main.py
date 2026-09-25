"""
main.py
=======
PARAKH FastAPI backend — read-only API over risk results.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .data_loader import data_store
from .routers import dashboard, projects, mps, alerts, agencies, reports, citizen

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("parakh.api")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Load data once at startup."""
    data_store.load_all()
    yield


app = FastAPI(
    title="PARAKH API",
    description="Project Anomaly & Risk Assessment Knowledge Hub — read-only API over MPLADS risk results.",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS — allow the Next.js dev server
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount routers
app.include_router(dashboard.router, prefix="/api/dashboard", tags=["Dashboard"])
app.include_router(projects.router, prefix="/api/projects", tags=["Projects"])
app.include_router(mps.router, prefix="/api/mps", tags=["MPs"])
app.include_router(alerts.router, prefix="/api/alerts", tags=["Alerts"])
app.include_router(agencies.router, prefix="/api/agencies", tags=["Agencies"])
app.include_router(reports.router, prefix="/api/reports", tags=["Reports"])
app.include_router(citizen.router, prefix="/api/citizen", tags=["Citizen Portal (D-032)"])


@app.get("/")
def root():
    return {
        "name": "PARAKH API",
        "version": "0.1.0",
        "docs": "/docs",
        "status": "healthy" if data_store.is_loaded else "loading",
    }


@app.get("/api/health")
def health():
    return {
        "status": "ok",
        "loaded": data_store.is_loaded,
        "risk_results_rows": len(data_store.risk_results) if data_store.risk_results is not None else 0,
    }
