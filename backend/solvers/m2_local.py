# -*- coding: utf-8 -*-
"""M2：M0-R + 局部改进（局部改进）。在 M0-R 的序列上做跨车/车内的 relocate 与 swap，
用近似单车成本（engine.route_cost）筛选，用引擎完整重放（现实口径、L1 总成本）确认，直到没有改进或预算用完。确定性，无随机。"""
import time
from typing import List, Optional

from ..costs import PriceTable
from ..engine import execute, route_cost
from ..models import Instance, Task
from .common import InfeasibleError, finalize
from .m0r import dispatch_m0r

EPS = 1e-6


def _total(inst, seqs, price):
    r = execute(inst, seqs, price)
    return None if r is None else r["cost"]["total"]


def improve(inst: Instance, seqs: List[List[Task]], price: PriceTable, budget_s: Optional[float] = 30.0):
    """返回 (改进后的序列, 实际总成本, 接受的移动数)。"""
    t0 = time.time()
    seqs = [list(s) for s in seqs]
    K = len(seqs)
    rc = [route_cost(inst, s, price)[0] if s else 0.0 for s in seqs]
    cur_cost = _total(inst, seqs, price)
    if cur_cost is None:
        raise InfeasibleError("起点序列在现实口径下无法排程")
    accepted = 0

    def out_of_time():
        return budget_s is not None and time.time() - t0 > budget_s

    improved = True
    while improved and not out_of_time():
        improved = False
        # ---- relocate ----
        for a in range(K):
            p = 0
            while p < len(seqs[a]) and not out_of_time():
                task = seqs[a][p]
                a_wo = seqs[a][:p] + seqs[a][p + 1:]
                rc_a_wo = route_cost(inst, a_wo, price)[0] if a_wo else 0.0
                best = None
                for b in range(K):
                    src = a_wo if b == a else seqs[b]
                    for q in range(len(src) + 1):
                        if b == a and q == p:
                            continue
                        cand = src[:q] + [task] + src[q:]
                        nb = route_cost(inst, cand, price)[0]
                        delta = (nb - rc[a]) if b == a else (rc_a_wo + nb - rc[a] - rc[b])
                        if delta < -EPS and (best is None or delta < best[0]):
                            best = (delta, b, q)
                if best is None:
                    p += 1
                    continue
                _d, b, q = best
                new = [list(s) for s in seqs]
                if b == a:
                    new[a] = a_wo[:q] + [task] + a_wo[q:]
                else:
                    new[a] = a_wo
                    new[b] = seqs[b][:q] + [task] + seqs[b][q:]
                c = _total(inst, new, price)
                if c is not None and c < cur_cost - EPS:
                    seqs, cur_cost = new, c
                    rc[a] = route_cost(inst, seqs[a], price)[0] if seqs[a] else 0.0
                    rc[b] = route_cost(inst, seqs[b], price)[0] if seqs[b] else 0.0
                    accepted += 1
                    improved = True
                else:
                    p += 1
        # ---- swap（不同车辆的两个任务互换）----
        for a in range(K):
            for b in range(a + 1, K):
                if out_of_time():
                    break
                for p in range(len(seqs[a])):
                    for q in range(len(seqs[b])):
                        na = seqs[a][:p] + [seqs[b][q]] + seqs[a][p + 1:]
                        nb = seqs[b][:q] + [seqs[a][p]] + seqs[b][q + 1:]
                        delta = route_cost(inst, na, price)[0] + route_cost(inst, nb, price)[0] - rc[a] - rc[b]
                        if delta < -EPS:
                            new = [list(s) for s in seqs]
                            new[a], new[b] = na, nb
                            c = _total(inst, new, price)
                            if c is not None and c < cur_cost - EPS:
                                seqs, cur_cost = new, c
                                rc[a] = route_cost(inst, na, price)[0]
                                rc[b] = route_cost(inst, nb, price)[0]
                                accepted += 1
                                improved = True
                                break
                    else:
                        continue
                    break
    return seqs, cur_cost, accepted


def solve_m2(inst: Instance, price: Optional[PriceTable] = None, budget_s: Optional[float] = 30.0) -> dict:
    price = price or PriceTable()
    start = dispatch_m0r(inst)
    start_cost = execute(inst, start, price)
    if start_cost is None:
        raise InfeasibleError("M0-R 起点无法排程")
    t0 = time.time()
    seqs, cost, n = improve(inst, start, price, budget_s)
    # 把被尾部剔除的任务也保留在序列里（execute 会再次剔除并计入外包），保证任务不丢
    return finalize(inst, seqs, price, "M2", {"extra": {"accepted_moves": n, "start_cost": start_cost["cost"]["total"],
                                                         "runtime_s": time.time() - t0}})
