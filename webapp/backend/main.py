from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import numpy as np
import json
import os
import sys

# Add project root to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

app = FastAPI(title="Supply Chain AI Dashboard", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    # Audit Section 6: explicit origin list — never use ["*"] in
    # production. Localhost dev origin only.
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    # Audit Section 6: scope methods to GET and POST only; the API
    # is read-only/scenario-eval. PUT/DELETE/PATCH not used.
    allow_methods=["GET", "POST", "OPTIONS"],
    # Audit Section 6: only Content-Type and standard headers needed
    allow_headers=["Content-Type", "Accept"],
    # 1-hour preflight cache to reduce OPTIONS chatter
    max_age=3600,
)

# Import routes
from routes.dashboard import router as dashboard_router
from routes.optimization import router as optimization_router
from routes.simulation import router as simulation_router
from routes.forecasting import router as forecasting_router
from schemas import HealthResponse

app.include_router(dashboard_router, prefix="/api/dashboard", tags=["dashboard"])
app.include_router(optimization_router, prefix="/api/optimization", tags=["optimization"])
app.include_router(simulation_router, prefix="/api/simulation", tags=["simulation"])
app.include_router(forecasting_router, prefix="/api/forecasting", tags=["forecasting"])


@app.get("/api/health", response_model=HealthResponse)
def health():
    return {"status": "ok", "version": "1.0.0"}
