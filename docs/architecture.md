# Architecture notes

## Pipeline

1. **Instance** — one day of orders (jobs = deliver a container, then collect one at the same customer), the fleet (tractors on duty, trailers per yard), travel times from a directed distance matrix.
2. **Solver** — any method returns only the task sequence of each tractor.
3. **Verifier** — re-plays every sequence in real-time order, checks feasibility (task assignment, return before the horizon, trailer inventory never negative) and computes every metric. No method reports its own score.
4. **Cost** — operating drivers × an editable price table. Prices carry a `source` tag (fictional / edited) and a currency; the front end only formats.
5. **Trajectory** — the verified plan expanded into per-truck segments along real road polylines. Total distance equals the verifier's number (checked by the tests in this repo; the full project also checks every arrival and finish time).

## Task and trailer semantics

- Four task types: deliver a loaded container (customer is a drop), deliver an empty, collect a loaded one, collect an empty. Deliveries need a trailer from a yard; collections end by returning the trailer to the nearest yard.
- Trailer yards are shared resources. The execution engine keeps a **time-ordered inventory timeline** per yard: a trailer can be hooked only if inventory stays non-negative at every moment after the insertion.
- Soft time windows: early and late arrival are both penalised per minute.

## Cost model

`cost = fuel(km) + driver hours + tractor fixed (per owned tractor) + trailer fixed + outsourced jobs + penalty minutes`

Design guard rails: the outsourcing price must exceed the cost of serving a job (otherwise an optimiser outsources instead of working), and fixed cost is per *owned* tractor (otherwise it parks tractors to look cheaper). Both are covered by tests.

## Two comparison views

With a fixed fleet, traditional trucking cannot finish every job and the rest is outsourced at an assumed price — which can flatter the traditional mode on light days. So the app also shows **each mode with the minimum number of tractors that serves every job**. That view does not depend on the outsourcing price.

## Real roads

Customer and yard points are fictional but sit on real roads (snapped to ≤250 m). Distances and route geometry for every ordered point pair come from OpenStreetMap through a local OSRM, **keeping one-way streets** (the way out and the way back can differ by a lot). The replay interpolates a truck's position along the polyline by distance travelled.

## API surface

`/api/network`, `/api/instances`, `/api/solve` → `/api/runs/{id}` (+ `/trajectory`), `/api/compare/run`, `/api/week`, `/api/recorded-runs`, `/api/price-table`. The API returns data and codes, never sentences; the UI renders them in the current language.

## Recorded plans

`data/recorded_runs/` holds a verified plan for each demo day (plan now and plan for tomorrow). Trajectories are rebuilt from the plan on request, so the replay opens instantly and survives server restarts.

## Limits

Prices, volumes and customer handling time are assumptions. Results come from a handful of seeds and short search budgets. There is no sensitivity analysis on handling time yet, no random-disruption simulation, and no real authentication (the login is a mock for the demo company).
