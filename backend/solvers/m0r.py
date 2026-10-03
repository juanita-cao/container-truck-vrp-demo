# -*- coding: utf-8 -*-
"""M0-R：经典三阶段启发式的"现实口径版"（规则不变，库存按真实时间判断）；M1：最早截止时间优先的朴素派工基线。

M0-R 的派工规则完全一致（紧迫度、同批牵引车与任务的排列、惩罚最小者优先），
唯一区别：取挂车时选"在到达该 TC 的那一刻有空挂"的最近 TC（engine.Timeline），而不是按派任务先后维护的计数。
"""
import itertools
from typing import List, Optional

from ..costs import PriceTable
from ..engine import Rec, Timeline, _make_rec, plan_transition
from ..models import Instance, Task
from .common import InfeasibleError, finalize

INF = float("inf")


def _urgency(inst: Instance):
    max_early = max((t.early_min for t in inst.tasks if not t.urgent), default=0)
    BIG = 2 ** 31 - 1
    return {id(t): (BIG if t.urgent else max_early - t.early_min) for t in inst.tasks}


def dispatch_m0r(inst: Instance) -> List[List[Task]]:
    urg = _urgency(inst)
    task_list: List[Task] = sorted(inst.tasks, key=lambda t: -urg[id(t)])
    K = inst.tractor_count
    cur: List[Optional[Rec]] = [None] * K
    seqs: List[List[Task]] = [[] for _ in range(K)]
    tl = Timeline(inst)

    def penalty(arrive, t):
        return max(t.early_min - arrive, 0) + max(arrive - t.late_min, 0)

    while task_list:
        if any(c is None for c in cur):
            avail = [i for i in range(K) if cur[i] is None]
        else:
            ef = min(c.finish for c in cur)
            avail = [i for i in range(K) if cur[i].finish == ef]
        top = urg[id(task_list[0])]
        n_top = 0
        for t in task_list:
            if urg[id(t)] != top:
                break
            n_top += 1
        special = task_list[0].urgent

        if len(avail) <= n_top:
            perms = itertools.permutations(range(n_top), len(avail))
            pairs_of = lambda p: [(avail[j], p[j]) for j in range(len(p))]
        else:
            perms = itertools.permutations(range(len(avail)), n_top)
            pairs_of = lambda p: [(avail[p[j]], j) for j in range(len(p))]

        best_cost, best_pairs = INF, None
        for p in perms:
            tmp = tl.copy()
            total = 0
            pairs = pairs_of(p)
            ok = True
            for ti, task_idx in pairs:
                t = task_list[task_idx]
                res = plan_transition(inst, cur[ti], t, tmp)
                if res is None:
                    ok = False
                    break
                for tc, tt, d in res[4]:
                    tmp.add(tc, tt, d)
                total += res[0] if special else penalty(res[0], t)
            if ok and best_cost > total:
                best_cost, best_pairs = total, pairs
        if best_pairs is None:
            raise InfeasibleError("所有候选排列都无法取到挂车")

        assigned = []
        for ti, task_idx in best_pairs:
            t = task_list[task_idx]
            res = plan_transition(inst, cur[ti], t, tl)
            for tc, tt, d in res[4]:
                tl.add(tc, tt, d)
            r = _make_rec(inst, t, res)
            cur[ti] = r
            seqs[ti].append(t)
            assigned.append(t)
        for t in assigned:
            task_list.remove(t)
    return seqs


def solve_m0r(inst: Instance, price: Optional[PriceTable] = None) -> dict:
    price = price or PriceTable()
    return finalize(inst, dispatch_m0r(inst), price, "M0-R")


def dispatch_edd(inst: Instance) -> List[List[Task]]:
    """M1：谁先空闲谁取"最晚开始时间最早"的任务（紧急任务最先），不看距离、不做排列优化。"""
    K = inst.tractor_count
    remaining = sorted(inst.tasks, key=lambda t: (0 if t.urgent else 1, t.late_min if not t.urgent else 0, t.id, t.sub))
    cur: List[Optional[Rec]] = [None] * K
    seqs: List[List[Task]] = [[] for _ in range(K)]
    tl = Timeline(inst)
    while remaining:
        if any(c is None for c in cur):
            k = next(i for i in range(K) if cur[i] is None)
        else:
            k = min(range(K), key=lambda i: (cur[i].finish, i))
        for t in remaining:
            res = plan_transition(inst, cur[k], t, tl)
            if res is not None:
                break
        else:
            raise InfeasibleError("没有任何任务可由该牵引车在现实口径下取到挂车")
        for tc, tt, d in res[4]:
            tl.add(tc, tt, d)
        cur[k] = _make_rec(inst, t, res)
        seqs[k].append(t)
        remaining.remove(t)
    return seqs


def dispatch_nearest(inst: Instance) -> List[List[Task]]:
    """M1：谁先空闲，谁就取"离自己最近"（本次转场+任务路程最短）的任务；完全不看时间窗，紧急任务除外（最先）。
    这是真正朴素的"谁近派谁"基线；dispatch_edd 是看时间窗的朴素规则，和既有的紧迫度规则很像，不适合当下限。"""
    K = inst.tractor_count
    remaining = sorted(inst.tasks, key=lambda t: (0 if t.urgent else 1, t.id, t.sub))
    cur: List[Optional[Rec]] = [None] * K
    seqs: List[List[Task]] = [[] for _ in range(K)]
    tl = Timeline(inst)
    while remaining:
        if any(c is None for c in cur):
            k = next(i for i in range(K) if cur[i] is None)
        else:
            k = min(range(K), key=lambda i: (cur[i].finish, i))
        best, best_res, best_t = None, None, None
        for t in remaining:
            res = plan_transition(inst, cur[k], t, tl)
            if res is None:
                continue
            key = (0 if t.urgent else 1, res[2])
            if best is None or key < best:
                best, best_res, best_t = key, res, t
        if best_t is None:
            raise InfeasibleError("没有任何任务可由该牵引车在现实口径下取到挂车")
        for tc, tt, d in best_res[4]:
            tl.add(tc, tt, d)
        cur[k] = _make_rec(inst, best_t, best_res)
        seqs[k].append(best_t)
        remaining.remove(best_t)
    return seqs


def solve_m1(inst: Instance, price: Optional[PriceTable] = None) -> dict:
    price = price or PriceTable()
    return finalize(inst, dispatch_nearest(inst), price, "M1")
