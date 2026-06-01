# Frontend — React Dashboard

Supply chain optimization dashboard built with React, Recharts, and Tailwind CSS.

## Start

```bash
cd webapp/frontend
npm install
npm run dev
# Open http://localhost:5173
```

Requires backend running on port 8000 (Vite proxies `/api` → `localhost:8000`).

## Pages

| Page | Component | Data Source |
|------|-----------|-------------|
| Overview | `Dashboard.jsx` | `/api/dashboard/summary` |
| Network | `NetworkMap.jsx` | `/api/dashboard/network-nodes` |
| Optimization | `ParetoChart.jsx` | `/api/optimization/pareto-front` |
| Resilience | `ResiliencePanel.jsx` | `/api/simulation/service-level` |
| Forecasting | `TrainingProgress.jsx` | `/api/forecasting/forecast` |
| Carbon | `CarbonBudget.jsx` | `/api/optimization/pareto-front` |

## Design

- Dark theme (zinc-950 background)
- No glassmorphism or gradients
- Consistent spacing and typography
- Empty states when data unavailable
- Real data only (no mock/placeholder data shown)

## Stack

- React 18 + Vite 5
- TanStack Query (data fetching)
- Recharts (charts)
- Tailwind CSS 3.4
- Lucide React (icons)
