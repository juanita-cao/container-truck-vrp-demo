# -*- coding: utf-8 -*-
"""C0：不甩挂（传统整车）对照——牵引车与挂车不能分离，到客户处要**等**客户装/卸完成，再带箱回枢纽。

要回答的问题：同样的货量、同样的车，用甩挂和不用甩挂差多少？所以只改"物理模式"，派工规则与模拟人工排班（H0）完全相同：
  1. 客户点按最近的挂车场分片区；早上按各片区的单数把牵引车分到片区；片区内先来先服务（按送箱时间窗开始的先后）；不跨片区调人。
  2. 一单 = 同一个客户点的 送箱 + 取箱，合成一趟往返：枢纽装箱（装卸 h）→ 行驶到客户 → **在客户处等该单的客户处理时间 W** → 行驶回枢纽 → 卸箱（装卸 h）。
     送箱任务的"开始时间" = 到达客户的时刻；取箱任务的"开始时间" = 到达 + W（等装卸完就带走）；早到/迟到按各自的时间窗折算（沿用旧口径：早到也惩罚，不等待）。
  3. 每辆牵引车带自己的挂车（挂车数 = 牵引车数），没有挂车池、不去挂车场。
  4. 一天结束时尾部超出规划期的单被剔除，计为未完成（外包）；任务数按"送箱 + 取箱"各算一个，与甩挂模式口径一致。
成本用同一张单价表（`costs.cost_breakdown`）。**不做优化**（用户要求简单做）。
"""
from typing import Dict, List, Optional

from .costs import PriceTable, cost_breakdown
from .models import Instance, S_TYPES, Task
from .solvers.manual_sim import allocate_drivers, merge_orphan_zones, zone_of_clients


def group_jobs(inst: Instance) -> Dict[int, Dict[str, Task]]:
    jobs: Dict[int, Dict[str, Task]] = {}
    for t in inst.tasks:
        if t.job is None or t.service_min is None:
            raise ValueError("不可分离对照需要成对的单（任务缺少 job / service_min）")
        jobs.setdefault(t.job, {})["S" if t.type in S_TYPES else "Q"] = t
    for j, v in jobs.items():
        if set(v) != {"S", "Q"}:
            raise ValueError(f"单 {j} 不是一对 送箱 + 取箱")
    return jobs


def solve_conventional(inst: Instance, price: Optional[PriceTable] = None) -> dict:
    price = price or PriceTable()
    D, H, hand, mins = inst.D, inst.horizon_min, inst.handling_min, inst.minutes
    K = inst.tractor_count
    jobs = group_jobs(inst)
    zone = zone_of_clients(inst)
    queues: Dict[int, List[int]] = {}
    for j, v in jobs.items():
        queues.setdefault(zone[v["S"].client_id], []).append(j)
    for z in queues:
        queues[z].sort(key=lambda j: (jobs[j]["S"].early_min, j))
    alloc = allocate_drivers(inst, {z: len(q) for z, q in queues.items()})
    merge_orphan_zones(queues, alloc, key=lambda j: (jobs[j]["S"].early_min, j))
    drivers = []
    k = 0
    for z in sorted(alloc):
        for _ in range(alloc[z]):
            drivers.append((k, z))
            k += 1

    free = [0] * K
    trips: List[List[dict]] = [[] for _ in range(K)]
    while any(queues.values()):
        cand = [(free[d], d, z) for d, z in drivers if queues.get(z)]
        f, d, z = min(cand)
        j = queues[z].pop(0)
        s, q = jobs[j]["S"], jobs[j]["Q"]
        cn = inst.client_node[s.client_id]
        arrive = f + hand + mins(D[0][cn])                       # 枢纽装箱后出发，到达客户
        pickup = arrive + s.service_min                          # 在客户处等装/卸完成
        back = pickup + mins(D[cn][0])                           # 带着箱子回枢纽
        done = back + hand                                       # 卸箱后空闲
        trips[d].append({"job": j, "s": s.label, "q": q.label, "start": f, "arrive": arrive, "pickup": pickup, "back": back, "free": done,
                         "km": D[0][cn] + D[cn][0], "wait": s.service_min})
        free[d] = done

    unfinished_jobs: List[int] = []
    for d in range(K):
        while trips[d] and trips[d][-1]["free"] > H:             # 尾部超出规划期：剔除（外包）
            unfinished_jobs.append(trips[d].pop()["job"])

    km = sum(t["km"] for tt in trips for t in tt)
    early = late = 0
    wait_min = 0
    for tt in trips:
        for t in tt:
            s, q = jobs[t["job"]]["S"], jobs[t["job"]]["Q"]
            early += max(s.early_min - t["arrive"], 0) + max(q.early_min - t["pickup"], 0)
            late += max(t["arrive"] - s.late_min, 0) + max(t["pickup"] - q.late_min, 0)
            wait_min += t["wait"]
    used = sum(1 for tt in trips if tt)
    driver_minutes = sum(tt[-1]["free"] for tt in trips if tt)
    unfinished_tasks = 2 * len(unfinished_jobs)
    cost = cost_breakdown(km, driver_minutes, K, used, K, early + late, unfinished_tasks, price)   # 挂车数 = 牵引车数
    n_tasks = len(inst.tasks)
    hit = sum(1 for tt in trips for t in tt
              for ok in ((jobs[t["job"]]["S"].early_min <= t["arrive"] <= jobs[t["job"]]["S"].late_min),
                         (jobs[t["job"]]["Q"].early_min <= t["pickup"] <= jobs[t["job"]]["Q"].late_min)) if ok)
    return {
        "method": "C0", "mode": "conventional",
        "plan": {"tractors": trips, "unfinished_jobs": sorted(unfinished_jobs)},
        "totals": {"unfinished": unfinished_tasks, "mileage_km": round(km, 2), "early_penalty": early, "late_penalty": late,
                   "total_penalty": early + late},
        "cost": cost, "on_time_rate": hit / n_tasks if n_tasks else None,
        "wait_hours": wait_min / 60.0, "tractors_used": used, "driver_minutes": driver_minutes,
    }
