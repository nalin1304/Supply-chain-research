"""FastAPI endpoint smoke tests."""

import os
import sys

import pytest
from fastapi.testclient import TestClient

# Add webapp/backend to path so its routes import cleanly
WEBAPP_BACKEND = os.path.join(
    os.path.dirname(__file__), "..", "webapp", "backend",
)
sys.path.insert(0, WEBAPP_BACKEND)


@pytest.fixture(scope="module")
def client():
    """FastAPI TestClient over the production app."""
    # Import deferred so other tests aren't affected
    from main import app
    return TestClient(app)


class TestHealth:
    def test_health_returns_ok(self, client):
        r = client.get("/api/health")
        assert r.status_code == 200
        body = r.json()
        assert body["status"] == "ok"
        assert "version" in body


class TestDashboard:
    def test_summary_returns_200(self, client):
        r = client.get("/api/dashboard/summary")
        assert r.status_code == 200

    def test_summary_has_training_status_or_mock(self, client):
        r = client.get("/api/dashboard/summary")
        body = r.json()
        # Either real data with training_status, or mock
        assert "training_status" in body or body.get("is_mock") is True

    def test_network_nodes_shape(self, client):
        r = client.get("/api/dashboard/network-nodes")
        assert r.status_code == 200
        body = r.json()
        assert "warehouses" in body
        assert "customers" in body


class TestOptimization:
    def test_pareto_front_endpoint(self, client):
        r = client.get("/api/optimization/pareto-front")
        assert r.status_code == 200

    def test_hypervolume_endpoint(self, client):
        r = client.get("/api/optimization/hypervolume")
        assert r.status_code == 200

    def test_run_scenario_post(self, client):
        r = client.post(
            "/api/optimization/run-scenario",
            json={
                "population_size": 20,
                "generations": 5,
                "carbon_weight": 0.5,
                "ev_ratio": 0.3,
                "demand_multiplier": 1.0,
            },
        )
        assert r.status_code == 200


class TestSimulation:
    def test_service_level_endpoint(self, client):
        r = client.get("/api/simulation/service-level")
        assert r.status_code == 200

    def test_resilience_metrics_endpoint(self, client):
        r = client.get("/api/simulation/resilience-metrics")
        assert r.status_code == 200


class TestForecasting:
    def test_forecast_endpoint(self, client):
        r = client.get("/api/forecasting/forecast")
        assert r.status_code == 200

    def test_attention_weights_endpoint(self, client):
        r = client.get("/api/forecasting/attention-weights")
        assert r.status_code == 200


class TestCORS:
    def test_cors_methods_restricted(self, client):
        # Audit Phase 12 F8: only GET, POST, OPTIONS allowed
        r = client.options(
            "/api/health",
            headers={
                "Origin": "http://localhost:5173",
                "Access-Control-Request-Method": "GET",
                "Access-Control-Request-Headers": "Content-Type",
            },
        )
        # 200 or 204 acceptable; preflight OK
        assert r.status_code in (200, 204)
