# -*- coding: utf-8 -*-
"""公开演示仓库的冒烟测试：只用虚构的新加坡数据，覆盖 接口 → 求解 → 独立校验 → 轨迹 的主链路。"""
import time

import pytest
from fastapi.testclient import TestClient

from backend import datasets
from backend.api.main import app
from backend.api import jobs
from backend.costs import default_price_table
from backend.solvers.m0r import solve_m0r
from backend.solvers.m2_local import solve_m2
from backend.verifier import verify

client = TestClient(app)


@pytest.fixture(scope="module")
def sun():
    return datasets.load("sg_sun", "demo_sg")


def test_health_and_network():
    assert client.get("/api/health").json()["status"] == "ok"
    net = client.get("/api/network").json()
    assert net["clients"] and net["yards"] and net["hub"]


def test_instances_listed():
    names = client.get("/api/instances", params={"dataset": "demo_sg"}).json()
    assert {n["name"] if isinstance(n, dict) else n for n in names} >= {"sg_mon", "sg_sun"}


def test_plans_are_feasible_and_local_search_does_not_lose(sun):
    price = default_price_table("demo_sg")
    base = solve_m0r(sun, price)
    better = solve_m2(sun, price, budget_s=5)
    for res in (base, better):
        assert verify(sun, res["plan"], inventory_mode="enforce")["feasible"]
    assert better["cost"]["total"] <= base["cost"]["total"] + 1e-6


def test_async_solve_and_trajectory():
    r = client.post("/api/solve", json={"dataset": "demo_sg", "instance": "sg_sun", "mode": "now"})
    assert r.status_code == 202
    rid = r.json()["run_id"]
    for _ in range(120):
        s = client.get(f"/api/runs/{rid}").json()
        if s["status"] not in ("QUEUED", "RUNNING"):
            break
        time.sleep(1)
    assert s["status"] == "DONE"
    tr = client.get(f"/api/runs/{rid}/trajectory")
    assert tr.status_code == 200 and tr.json()["tractors"]


def test_public_budget_cap():
    r = client.post("/api/solve", json={"dataset": "demo_sg", "instance": "sg_sun", "mode": "tomorrow",
                                         "budget_s": jobs.MAX_BUDGET + 1})
    assert r.status_code == 400
