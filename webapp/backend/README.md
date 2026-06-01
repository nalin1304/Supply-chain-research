# Backend — FastAPI

Serves real training results to the React dashboard.

## Start

```bash
cd webapp/backend
uvicorn main:app --reload --port 8000
```

## Endpoints

| Endpoint | Returns |
|----------|---------|
| `GET /api/health` | Server status |
| `GET /api/dashboard/summary` | KPIs (cost, emissions, service level) |
| `GET /api/dashboard/network-nodes` | Warehouse + customer locations |
| `GET /api/optimization/pareto-front` | Pareto-optimal solutions |
| `GET /api/optimization/hypervolume` | HV convergence history |
| `POST /api/optimization/run-scenario` | Custom scenario (synthetic) |
| `GET /api/simulation/service-level` | MC service level distribution |
| `GET /api/simulation/resilience-metrics` | TTS, TTR metrics |
| `POST /api/simulation/run-shock` | Custom shock simulation |
| `GET /api/forecasting/forecast` | LSTM predictions vs actuals |
| `GET /api/forecasting/attention-weights` | Feature importance |

All endpoints return `is_mock: false` when real training data exists in `data/results/`.

## Data Source

Reads from `../../data/results/` (relative to backend directory):
- `training_summary.json` — overall metrics
- `nsga2_best_front.npy` — Pareto front points
- `nsga2_all_results.pkl` — all seeds + HV histories
- `lstm_predictions.npy` / `lstm_actuals.npy` — forecast data
- `mc_service_levels.npy` — Monte Carlo results
