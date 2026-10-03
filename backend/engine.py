# -*- coding: utf-8 -*-
"""现实口径执行引擎：给定每辆牵引车的任务序列，按真实时间顺序重放，
自动选择取/还挂车的 TC，保证 TC 库存在任何时刻不为负，产出 Plan 与全部指标。

与旧口径的区别：旧口径按"派任务的先后"更新库存；这里按"真实时间"维护每个 TC 的取/还事件时间线，
取挂车前检查"插入这次取挂车后，时间线上任何时刻库存都不为负"。时间/路径公式与既有规则一致（见 verifier.py 的语义说明）。
最终以独立校验器为准（verify(..., inventory_mode="enforce")）。
"""
import bisect
from typing import List, Optional

from .costs import PriceTable, cost_breakdown
from .models import Instance, Q_TYPES, S_TYPES, Task


class Timeline:
    """每个 TC 的取(-1)/还(+1)事件时间线；同一时刻先还后取。"""
    __slots__ = ("ev", "init")

    def __init__(self, inst: Instance, ev=None):
        self.init = {tc: inst.tcs[tc - inst.tc_first]["trailers"] for tc in inst.tc_nodes()}
        self.ev = ev if ev is not None else {tc: [] for tc in inst.tc_nodes()}

    def copy(self) -> "Timeline":
        t = Timeline.__new__(Timeline)
        t.init = self.init
        t.ev = {k: list(v) for k, v in self.ev.items()}
        return t

    def fetch_ok(self, tc: int, t: int) -> bool:
        lvl = self.init[tc]
        key = (t, 1)
        inserted = False
        for tt, o, d in self.ev[tc]:
            if not inserted and (tt, o) > key:
                lvl -= 1
                if lvl < 0:
                    return False
                inserted = True
            lvl += d
            if lvl < 0:
                return False
        if not inserted:
            lvl -= 1
        return lvl >= 0

    def add(self, tc: int, t: int, delta: int):
        bisect.insort(self.ev[tc], (t, 0 if delta > 0 else 1, delta))


class Rec:
    __slots__ = ("task", "node", "start", "finish", "dist", "tc", "ends_at_dc", "early", "late")

    def __init__(self, task: Task, node: int):
        self.task, self.node = task, node
        self.start = self.finish = 0
        self.dist = 0.0
        self.tc = None
        self.ends_at_dc = task.type in Q_TYPES
        self.early = self.late = 0


def nearest_tc_return(inst: Instance, to_node: int) -> int:
    """argmin D[0,tc]+D[tc,to]（还挂车，不检查库存），平局取先出现者。"""
    D = inst.D
    best, best_tc = None, None
    for i in inst.tc_nodes():
        d = D[0][i] + D[i][to_node]
        if best is None or best > d:
            best, best_tc = d, i
    return best_tc


def plan_transition(inst: Instance, cur: Optional[Rec], nt: Task, tl: Timeline):
    """计算 cur → nt 的转场：返回 (arrive, finish, dist, tc|None, events)；取挂车无可用 TC 时返回 None。"""
    D, hand, mins = inst.D, inst.handling_min, inst.minutes
    cn = inst.client_node[nt.client_id]
    tc, ev = None, []
    if cur is None:
        if nt.type in S_TYPES:
            best = None
            for i in inst.tc_nodes():
                if tl.fetch_ok(i, mins(D[0][i])):
                    d = D[0][i] + D[i][0]
                    if best is None or best > d:
                        best, tc = d, i
            if tc is None:
                return None
            dist = D[0][tc] + D[tc][0] + D[0][cn]
            arrive = mins(dist) + hand
            finish = arrive
            ev.append((tc, mins(D[0][tc]), -1))
        else:
            d1 = D[0][cn]
            arrive = mins(d1)
            dist = d1 + D[cn][0]
            finish = mins(dist)
    else:
        cc = cur.node
        if cur.task.type in Q_TYPES:
            if nt.type in Q_TYPES:
                tc = nearest_tc_return(inst, cn)
                d1 = D[0][tc] + D[tc][cn]
                arrive = cur.finish + mins(d1) + hand
                dist = d1 + D[cn][0]
                finish = cur.finish + mins(dist) + hand
                ev.append((tc, cur.finish + mins(D[0][tc]), +1))
            else:
                dist = D[0][cn]
                arrive = cur.finish + mins(dist) + hand * 2
                finish = arrive
        else:
            if nt.type in Q_TYPES:
                d1 = D[cc][cn]
                arrive = cur.finish + mins(d1)
                dist = d1 + D[cn][0]
                finish = cur.finish + mins(dist)
            else:
                best = None
                for i in inst.tc_nodes():
                    if tl.fetch_ok(i, cur.finish + mins(D[cc][i])):
                        d = D[cc][i] + D[i][0]
                        if best is None or best > d:
                            best, tc = d, i
                if tc is None:
                    return None
                dist = D[cc][tc] + D[tc][0] + D[0][cn]
                arrive = cur.finish + mins(dist) + hand
                finish = arrive
                ev.append((tc, cur.finish + mins(D[cc][tc]), -1))
    return arrive, finish, dist, tc, ev


def _make_rec(inst, nt, res) -> Rec:
    arrive, finish, dist, tc, _ev = res
    r = Rec(nt, inst.client_node[nt.client_id])
    r.start, r.finish, r.dist, r.tc = arrive, finish, dist, tc
    if not nt.urgent:
        r.early = max(nt.early_min - arrive, 0)
        r.late = max(arrive - nt.late_min, 0)
    return r


def _run(inst: Instance, seqs: List[List[Task]]):
    K = len(seqs)
    tl = Timeline(inst)
    cur: List[Optional[Rec]] = [None] * K
    lists: List[List[Rec]] = [[] for _ in range(K)]
    idx = [0] * K
    while True:
        best, bt = None, None
        for k in range(K):
            if idx[k] < len(seqs[k]):
                dt = 0 if cur[k] is None else cur[k].finish
                if best is None or dt < bt:
                    best, bt = k, dt
        if best is None:
            return lists
        nt = seqs[best][idx[best]]
        res = plan_transition(inst, cur[best], nt, tl)
        if res is None:
            return None
        for tc, t, d in res[4]:
            tl.add(tc, t, d)
        r = _make_rec(inst, nt, res)
        lists[best].append(r)
        cur[best] = r
        idx[best] += 1


def _trim_and_back(inst: Instance, lists: List[List[Rec]]):
    """剔除尾部完成时刻/回 DC 时刻超出规划期的任务；返回 (被剔除的任务, 每车回程距离, 每车回程时刻)。"""
    H, hand, mins, D = inst.horizon_min, inst.handling_min, inst.minutes, inst.D
    K = len(lists)
    dropped: List[Task] = []
    back_d, back_t = [0.0] * K, [0] * K
    for i in range(K):
        recs = lists[i]
        while recs:
            last = recs[-1]
            if last.finish > H:
                dropped.append(last.task)
                recs.pop()
                continue
            if not last.ends_at_dc:
                bd = D[last.node][0]
                bt = mins(bd) + last.finish
            else:
                tcn = nearest_tc_return(inst, 0)
                bd = D[0][tcn] + D[tcn][0]
                bt = mins(bd) + hand + last.finish
            if bt > H:
                dropped.append(last.task)
                recs.pop()
            else:
                back_d[i], back_t[i] = bd, bt
                break
    return dropped, back_d, back_t


def execute(inst: Instance, seqs: List[List[Task]], price: Optional[PriceTable] = None, trailers_total=None):
    """按真实时间重放序列并整理成结果；序列在现实口径下无法排程（无可用 TC）时返回 None。"""
    price = price or PriceTable()
    seqs = [list(s) for s in seqs]
    for _ in range(6):
        lists = _run(inst, seqs)
        if lists is None:
            return None
        dropped, back_d, back_t = _trim_and_back(inst, lists)
        if not dropped:
            break
        seqs = [[r.task for r in l] for l in lists]
    else:
        return None
    scheduled = {t.label for l in lists for t in (r.task for r in l)}
    unfinished = [t for t in inst.tasks if t.label not in scheduled]

    tc_id = lambda n: None if n is None else inst.tcs[n - inst.tc_first]["id"]
    plan = {"tractors": [[{"task": r.task.label, "tc": tc_id(r.tc)} for r in l] for l in lists],
            "unfinished": [t.label for t in unfinished]}
    km = sum(r.dist for l in lists for r in l) + sum(back_d)
    early = sum(r.early for l in lists for r in l)
    late = sum(r.late for l in lists for r in l)
    used = sum(1 for l in lists if l)
    drv = sum(back_t[i] for i, l in enumerate(lists) if l)
    trailers = trailers_total if trailers_total is not None else sum(t["trailers"] for t in inst.tcs)
    unf_ids = {t.id for t in unfinished}
    cost = cost_breakdown(km, drv, inst.tractor_count, used, trailers, early + late, len(unf_ids), price)
    totals = {"unfinished": len(unf_ids), "mileage_km": round(km, 2), "early_penalty": early,
              "late_penalty": late, "total_penalty": early + late}
    return {"plan": plan, "totals": totals, "cost": cost, "end_times": back_t, "seqs": [[r.task for r in l] for l in lists]}


def route_cost(inst: Instance, seq: List[Task], price: PriceTable):
    """单车路线的近似成本（忽略库存耦合，TC 取最近者）：用于搜索中的快速筛选。
    返回 (cost, km, end_time, penalty_minutes, dropped_count)。"""
    D, H, hand, mins = inst.D, inst.horizon_min, inst.handling_min, inst.minutes
    tcs = list(inst.tc_nodes())
    cur_node, cur_finish, cur_type = 0, 0, None
    recs = []  # (finish, dist, early+late, ends_at_dc, node)
    for nt in seq:
        cn = inst.client_node[nt.client_id]
        if cur_type is None:
            if nt.type in S_TYPES:
                tc = min(tcs, key=lambda i: D[0][i] + D[i][0])
                dist = D[0][tc] + D[tc][0] + D[0][cn]
                arrive = mins(dist) + hand
                finish = arrive
            else:
                dist = D[0][cn] + D[cn][0]
                arrive = mins(D[0][cn])
                finish = mins(dist)
        elif cur_type in Q_TYPES:
            if nt.type in Q_TYPES:
                tc = nearest_tc_return(inst, cn)
                d1 = D[0][tc] + D[tc][cn]
                arrive = cur_finish + mins(d1) + hand
                dist = d1 + D[cn][0]
                finish = cur_finish + mins(dist) + hand
            else:
                dist = D[0][cn]
                arrive = cur_finish + mins(dist) + hand * 2
                finish = arrive
        else:
            if nt.type in Q_TYPES:
                d1 = D[cur_node][cn]
                arrive = cur_finish + mins(d1)
                dist = d1 + D[cn][0]
                finish = cur_finish + mins(dist)
            else:
                tc = min(tcs, key=lambda i: D[cur_node][i] + D[i][0])
                dist = D[cur_node][tc] + D[tc][0] + D[0][cn]
                arrive = cur_finish + mins(dist) + hand
                finish = arrive
        pen = 0 if nt.urgent else max(nt.early_min - arrive, 0) + max(arrive - nt.late_min, 0)
        recs.append((finish, dist, pen, nt.type in Q_TYPES, cn))
        cur_node, cur_finish, cur_type = cn, finish, nt.type
    dropped = 0
    back_d, back_t = 0.0, 0
    while recs:
        finish, _d, _p, at_dc, node = recs[-1]
        if finish > H:
            recs.pop(); dropped += 1; continue
        if not at_dc:
            bd = D[node][0]; bt = mins(bd) + finish
        else:
            tcn = nearest_tc_return(inst, 0); bd = D[0][tcn] + D[tcn][0]; bt = mins(bd) + hand + finish
        if bt > H:
            recs.pop(); dropped += 1
        else:
            back_d, back_t = bd, bt
            break
    km = sum(r[1] for r in recs) + back_d
    pen = sum(r[2] for r in recs)
    cost = (km * price.fuel_l_per_100km / 100 * price.fuel_price_per_l + (back_t / 60 * price.driver_per_hour if recs else 0)
            + pen * price.penalty_per_minute + dropped * price.outsource_per_task)
    return cost, km, back_t, pen, dropped
