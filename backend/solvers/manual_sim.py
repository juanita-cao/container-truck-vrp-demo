# -*- coding: utf-8 -*-
"""H0：模拟的人工排班（演示用对照，**不是真实调度员数据**）。

按调度员常见的经验做法建模，规则透明、不为凑数字调参：
  1. 分片：每个客户点归属"离它最近的挂车场"所在的片区（调度员熟悉的老地盘）。
  2. 早上定编：按各片区当天的任务数，按比例把牵引车分给各片区（每个有任务的片区至少 1 辆）；当天不再跨片区调人。
  3. 先来先服务：片区内的任务按时间窗开始的先后排队；谁先空下来谁接队首任务。紧急任务排最前。
  4. 不做全局优化：不重排顺序、不拼箱（送完不顺路取箱）、不跨片区平衡负载。
典型弱点就是这些规则带来的：片区之间忙闲不均、跑空程多、时间窗满足得差。结果与算法的差距由规则自然产生，不人为放大。
"""
from typing import Dict, List, Optional

from ..costs import PriceTable
from ..engine import Rec, Timeline, _make_rec, plan_transition
from ..models import Instance, Task
from .common import InfeasibleError, finalize


def zone_of_clients(inst: Instance) -> Dict[int, int]:
    """客户点 → 片区（最近挂车场的节点号）。"""
    D = inst.D
    zones = {}
    for c in inst.clients:
        n = inst.client_node[c["id"]]
        zones[c["id"]] = min(inst.tc_nodes(), key=lambda tc: (D[n][tc] + D[tc][n], tc))
    return zones


def allocate_drivers(inst: Instance, counts: Dict[int, int]) -> Dict[int, int]:
    """按各片区任务数比例分配牵引车（最大余数法；有任务的片区至少 1 辆）。"""
    K = inst.tractor_count
    active = [z for z, n in counts.items() if n > 0]
    total = sum(counts[z] for z in active)
    base = {z: max(1, int(K * counts[z] / total)) for z in active}
    while sum(base.values()) > K:                      # 极端情况下超配，从最多的片区扣
        z = max(base, key=lambda z: (base[z], z))
        base[z] -= 1
    rest = K - sum(base.values())
    order = sorted(active, key=lambda z: -(K * counts[z] / total - base[z]))
    i = 0
    while rest > 0 and order:
        base[order[i % len(order)]] += 1
        rest -= 1
        i += 1
    return base


def merge_orphan_zones(queues: Dict[int, list], alloc: Dict[int, int], key) -> None:
    """车辆数少于片区数时，有的片区分不到车：它的任务并入车最多的片区去做（调度员实际会这么处理），并按 key 重新排队。"""
    donor = max(alloc, key=lambda z: (alloc[z], -z))
    for z in [z for z, n in alloc.items() if n == 0]:
        queues[donor] = sorted(queues[donor] + queues.pop(z, []), key=key)
        del alloc[z]


def dispatch_manual(inst: Instance) -> List[List[Task]]:
    K = inst.tractor_count
    zone = zone_of_clients(inst)
    queues: Dict[int, List[Task]] = {}
    for t in inst.tasks:
        queues.setdefault(zone[t.client_id], []).append(t)
    for z in queues:
        queues[z].sort(key=lambda t: (0 if t.urgent else 1, t.early_min if not t.urgent else 0, t.id, t.sub))
    alloc = allocate_drivers(inst, {z: len(q) for z, q in queues.items()})
    merge_orphan_zones(queues, alloc, key=lambda t: (0 if t.urgent else 1, t.early_min if not t.urgent else 0, t.id, t.sub))
    drivers: List[tuple] = []                           # (牵引车序号, 片区)
    k = 0
    for z in sorted(alloc):
        for _ in range(alloc[z]):
            drivers.append((k, z))
            k += 1
    cur: List[Optional[Rec]] = [None] * K
    seqs: List[List[Task]] = [[] for _ in range(K)]
    tl = Timeline(inst)
    while any(queues.values()):
        cand = [(0 if cur[d] is None else cur[d].finish, d, z) for d, z in drivers if queues.get(z)]
        _t, d, z = min(cand)
        t = queues[z][0]
        res = plan_transition(inst, cur[d], t, tl)
        if res is None:
            raise InfeasibleError("人工排班：该片区取不到挂车")
        for tc, tt, dl in res[4]:
            tl.add(tc, tt, dl)
        cur[d] = _make_rec(inst, t, res)
        seqs[d].append(t)
        queues[z].pop(0)
    return seqs


def solve_manual(inst: Instance, price: Optional[PriceTable] = None) -> dict:
    price = price or PriceTable()
    res = finalize(inst, dispatch_manual(inst), price, "H0")
    res["extra"] = {"note": "模拟的人工排班（片区+先来先服务），演示用，非真实调度员数据"}
    return res
