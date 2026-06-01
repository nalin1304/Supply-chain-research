# Supply Chain AI Dashboard

Full-stack web application for visualizing and interacting with the Supply Chain AI Research project.

## Architecture

- **Backend**: FastAPI (Python) — serves optimization results, runs scenarios, exposes trained models
- **Frontend**: React + Vite — modern dashboard with interactive charts, maps, and controls

## Quick Start

### Backend

```bash
cd webapp/backend
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

The API will be available at `http://localhost:8000`. API docs at `http://localhost:8000/docs`.

### Frontend (separate terminal)

```bash
cd webapp/frontend
npm install
npm run dev
```

The dashboard will be available at `http://localhost:5173`.

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/health` | GET | Health check |
| `/api/dashboard/summary` | GET | KPI summary metrics |
| `/api/optimization/pareto-front` | GET | NSGA-II Pareto front points |
| `/api/optimization/hypervolume` | GET | Hypervolume convergence |
| `/api/optimization/run-scenario` | POST | Run custom NSGA-II scenario |
| `/api/simulation/service-level` | GET | Daily service level array |
| `/api/simulation/resilience-metrics` | GET | TTS, TTR, max drop |
| `/api/simulation/run-shock` | POST | Run DES with shock event |
| `/api/forecasting/forecast` | GET | 7-day demand forecast |
| `/api/forecasting/attention-weights` | GET | Attention heatmap data |

## Development

Both servers support hot-reload during development. The frontend proxies API calls to the backend via the Vite dev server configuration.
