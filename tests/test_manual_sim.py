# -*- coding: utf-8 -*-
"""H0 模拟人工排班（片区 + 先来先服务）：可行、确定性、规则本身的性质；并确认它在一周里整体比优化方法差（规则自然产生，不是调出来的）。"""
import sys
from collections import Counter
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from backend import datasets  # noqa: E402
from backend.costs import PriceTable  # noqa: E402
from backend.solvers.m2_local import solve_m2  # noqa: E402
from backend.solvers.manual_sim import allocate_drivers, dispatch_manual, solve_manual, zone_of_clients  # noqa: E402
from backend.verifier import verify  # noqa: E402

PRICE = PriceTable()
DAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]


@pytest.mark.parametrize("day", DAYS)
def test_manual_plan_is_feasible_and_complete(day):
    inst = datasets.load(f"sg_{day}", "demo_sg")
    r = solve_manual(inst, PRICE)
    rep = verify(inst, r["plan"], inventory_mode="enforce")
    assert rep["feasible"], rep["violations"]
    scheduled = {e["task"] for tr in r["plan"]["tractors"] for e in tr}
    assert len(scheduled) + len(r["plan"]["unfinished"]) == len(inst.tasks)
    assert "模拟" in r["extra"]["note"]


def test_manual_is_deterministic():
    inst = datasets.load("sg_mon", "demo_sg")
    assert solve_manual(inst, PRICE)["plan"] == solve_manual(inst, PRICE)["plan"]


def test_manual_never_crosses_zones_and_drivers_are_allocated_by_zone_load():
    inst = datasets.load("sg_mon", "demo_sg")
    zone = zone_of_clients(inst)
    by_label = {t.label: t for t in inst.tasks}
    seqs = dispatch_manual(inst)
    for s in seqs:
        assert len({zone[t.client_id] for t in s}) <= 1            # 一辆车只在自己的片区里跑
    counts = Counter(zone[t.client_id] for t in inst.tasks)
    alloc = allocate_drivers(inst, counts)
    assert sum(alloc.values()) == inst.tractor_count
    assert all(alloc[z] >= 1 for z in counts)
    assert max(counts, key=counts.get) in [z for z, v in alloc.items() if v == max(alloc.values())]   # 任务最多的片区车最多


def test_manual_is_worse_than_optimised_plans_over_the_week():
    """整周合计：人工（片区+先来先服务）比 M2 贵——这是规则自然产生的差距，不是调出来的。"""
    man = opt = 0.0
    for day in DAYS:
        inst = datasets.load(f"sg_{day}", "demo_sg")
        man += solve_manual(inst, PRICE)["cost"]["total"]
        opt += solve_m2(inst, PRICE, budget_s=10)["cost"]["total"]
    assert man > opt * 1.1
