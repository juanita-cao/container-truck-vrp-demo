# Drayage Planner — drop-and-pull container trucking demo

An end-to-end demo of a decision-support product for container drayage: **how much does drop-and-pull (leaving the trailer at the customer) save compared with trucks that wait at the customer, and how much more can optimisation save on top of that?**

Everything shown is **fictional** (a made-up company, *Bluewave Drayage Co.*, with made-up customers, volumes and unit prices) placed on the **real road network of Singapore**. Money figures are in SGD and depend on assumed unit prices that you can edit in the app.

## What is inside

- **Story line (Compare page):** traditional (non-detachable) → drop-and-pull with a manual-style dispatch rule → drop-and-pull with fast local search → drop-and-pull with ALNS. All four use the same orders and the same price table; two views are shown (each mode with the trucks it needs / the same number of trucks).
- **Input page:** edit orders and fleet, copy a day, save "my scenario", compare it live.
- **Network replay:** trucks move along real roads (OSM + OSRM, direction-aware distances), trailer state, yard inventory, event log, single-truck mode.
- **Bilingual UI** (English / 中文), money-first KPIs, user guide inside the app.
- **Methods:** simulated manual dispatch, a classic urgency-based dispatch rule, nearest-task rule, local search (relocate/swap), ALNS, exact CP-SAT on small slices (used as a ruler, not as a delivery method).
- **Independent verifier:** every plan from every method is re-played by one verifier that checks feasibility and computes all metrics; trajectories used by the replay agree with the verifier number by number.

## Honest limits

Prices, volumes and the customer handling-time range are assumptions. Results are demo-grade (few seeds, short budgets). The comparison is very sensitive to customer handling time; a sensitivity curve is not yet included. Simulation under random disruption and in-day re-planning are not implemented.

## Run locally

```bash
pip install -r requirements.txt
DATASET=demo_sg uvicorn backend.api.main:app --port 8000
cd frontend && npm ci && npm run dev      # http://localhost:5173
python -m pytest tests -q
```

## Deploy

`render.yaml` describes a Render blueprint (API web service + static front end). The API needs no external services; road geometry is precomputed in `data/company/`.

## Layout

`backend/` solvers, verifier, engine, API · `frontend/` React + Arco Design · `data/` fictional company, instances · `outputs/` precomputed comparison results · `tests/`

Map data © OpenStreetMap contributors.
