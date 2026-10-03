# -*- coding: utf-8 -*-
"""预录运行：每个演示日都有"立即排程/明日排程"两份，打开即可回放；轨迹由计划展开并与校验器一致。"""
import pytest
from fastapi.testclient import TestClient

from backend.api.main import app

client = TestClient(app)
DAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]


def test_every_demo_day_has_both_recorded_plans():
    rows = client.get("/api/recorded-runs", params={"dataset": "demo_sg"}).json()
    have = {(r["instance"], r["mode"]) for r in rows}
    assert have == {(f"sg_{d}", m) for d in DAYS for m in ("now", "tomorrow")}
    assert all(r["recorded"] for r in rows)


@pytest.mark.parametrize("day", ["mon", "sun"])
def test_recorded_run_is_feasible_and_replayable(day):
    rid = f"rec-sg_{day}-tomorrow"
    run = client.get(f"/api/runs/{rid}").json()
    assert run["status"] == "DONE" and run["recorded"] and run["verified"]["feasible"]
    assert run["cost"]["total"] > 0 and run["currency"] == "SGD"
    tr = client.get(f"/api/runs/{rid}/trajectory")
    assert tr.status_code == 200
    assert tr.json()["tractors"] and abs(tr.json()["km_total"] - run["totals"]["mileage_km"]) < 0.5


def test_tomorrow_plan_never_costs_more_than_now_plan():
    for d in DAYS:
        now = client.get(f"/api/runs/rec-sg_{d}-now").json()["cost"]["total"]
        tom = client.get(f"/api/runs/rec-sg_{d}-tomorrow").json()["cost"]["total"]
        assert tom <= now + 1e-6, d
