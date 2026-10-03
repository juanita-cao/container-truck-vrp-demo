# -*- coding: utf-8 -*-
"""不甩挂（传统整车）对照 C0：数字可手算核对；每个任务恰好被计一次；甩挂的优势随客户处理时间变化的方向正确。"""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from backend import datasets  # noqa: E402
from backend.conventional import group_jobs, solve_conventional  # noqa: E402
from backend.costs import default_price_table  # noqa: E402
from backend.models import Instance, Task  # noqa: E402
from backend.solvers.manual_sim import solve_manual  # noqa: E402

PRICE = default_price_table("demo_sg")
DAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]


def _tiny(service=120, tractors=1):
    # 节点 0=枢纽，1=客户点，2=挂车场；距离 DC↔客户 30 km，速度 60 km/h → 单程 30 分钟
    D = [[0, 30, 5], [30, 0, 30], [5, 30, 0]]
    tasks = [Task(1, 1, "SZ", 0, 120, job=1, service_min=service), Task(2, 1, "QK", service, service + 120, job=1, service_min=service)]
    return Instance(id="t", name="t", horizon_min=720, speed_kmh=60, handling_min=30, dc=(0, 0), tractor_count=tractors,
                    clients=[{"id": 1, "x": 1, "y": 1}], tcs=[{"id": 1, "x": 0.1, "y": 0.1, "trailers": 5}], tasks=tasks,
                    coord_system="wgs84", distance_matrix=D)


def test_hand_computed_single_trip():
    r = solve_conventional(_tiny(service=120))
    t = r["plan"]["tractors"][0][0]
    # 装箱 30 + 行驶 30 → 到达 60；等 120 → 取箱 180；回程 30 → 回枢纽 210；卸箱 30 → 空闲 240
    assert (t["arrive"], t["pickup"], t["back"], t["free"]) == (60, 180, 210, 240)
    assert r["totals"]["mileage_km"] == 60.0 and r["totals"]["unfinished"] == 0
    assert r["totals"]["total_penalty"] == 0                 # 送箱窗口 [0,120] 内到达；取箱窗口 [120,240] 内取走
    assert r["wait_hours"] == pytest.approx(2.0)


def test_trip_beyond_horizon_is_unfinished_and_counts_two_tasks():
    r = solve_conventional(_tiny(service=700))
    assert r["totals"]["unfinished"] == 2 and r["plan"]["unfinished_jobs"] == [1]


def test_requires_paired_jobs():
    inst = _tiny()
    inst.tasks[1].job = None
    with pytest.raises(ValueError):
        solve_conventional(inst)


@pytest.mark.parametrize("day", DAYS)
def test_every_task_is_counted_exactly_once_on_the_weekly_data(day):
    inst = datasets.load(f"sg_{day}", "demo_sg")
    r = solve_conventional(inst, PRICE)
    done = sum(2 for tt in r["plan"]["tractors"] for _ in tt)
    assert done + r["totals"]["unfinished"] == len(inst.tasks)
    assert len(group_jobs(inst)) * 2 == len(inst.tasks)
    for tt in r["plan"]["tractors"]:                         # 同一辆车的趟次不重叠
        for a, b in zip(tt, tt[1:]):
            assert b["start"] >= a["free"]


def test_longer_customer_handling_hurts_conventional_more_than_drop_and_pull():
    """同一批货、同样的车：客户处理时间变长时，不甩挂的成本涨得比甩挂多（甩挂的牵引车不用在客户处等）。"""
    inst = datasets.load("sg_mon", "demo_sg")

    def with_service(w):
        for t in inst.tasks:
            t.service_min = w
        return inst

    gaps = []
    for w in (60, 360):
        i = with_service(w)
        conv = solve_conventional(i, PRICE)["cost"]["total"]
        dp = solve_manual(i, PRICE)["cost"]["total"]
        gaps.append(conv - dp)
    assert gaps[1] > gaps[0]
