# -*- coding: utf-8 -*-
"""M3：ALNS（自适应大邻域搜索，元启发式）。

起点 = M0-R；每轮"拆"掉一批任务（随机 / 最差 / 相关）再"修"回去（贪心 / 后悔-2），
用引擎完整重放（现实口径，L1 总成本）判断，模拟退火式接受；算子按近期表现自适应加权。
- 随机：给定 seed 与 max_iter 时结果完全可重现；按时间预算停止时，迭代数取决于机器速度。
- 全程记录"当前最优成本随时间"（trace），一次运行得到整条质量—时间曲线。
"""
import math
import random
import time
from typing import List, Optional

from ..costs import PriceTable
from ..engine import execute, route_cost
from ..models import Instance, Task
from .common import InfeasibleError, finalize, route_costs
from .m2_local import improve
from .m0r import dispatch_m0r


def _all_tasks(seqs):
    return [(k, t) for k, s in enumerate(seqs) for t in s]


def _remove(seqs, tasks):
    ids = {id(t) for t in tasks}
    return [[t for t in s if id(t) not in ids] for s in seqs]


def solve_m3(inst: Instance, price: Optional[PriceTable] = None, budget_s: Optional[float] = 60.0,
             seed: int = 0, max_iter: Optional[int] = None, progress=None, cancel=None) -> dict:
    """progress(elapsed_s, best_cost, iterations) 每 25 次迭代回调一次；cancel 是 threading.Event，置位后在下一次迭代前停止并返回当前最优。"""
    price = price or PriceTable()
    rng = random.Random(seed)
    t_start = time.time()
    n_tasks = len(inst.tasks)

    start = dispatch_m0r(inst)
    first = execute(inst, start, price)
    if first is None:
        raise InfeasibleError("M0-R 起点无法排程")
    cur = [list(s) for s in start]
    cur_cost = first["cost"]["total"]
    best, best_cost = [list(s) for s in cur], cur_cost
    trace = [(0.0, best_cost)]

    # ---- 算子 ----
    def destroy_random(seqs, q):
        pool = [t for _k, t in _all_tasks(seqs)]
        return rng.sample(pool, min(q, len(pool)))

    def destroy_worst(seqs, q):
        rc = route_costs(inst, seqs, price)
        gains = []
        for k, s in enumerate(seqs):
            for i, t in enumerate(s):
                wo = s[:i] + s[i + 1:]
                gains.append((rc[k] - (route_cost(inst, wo, price)[0] if wo else 0.0), t))
        gains.sort(key=lambda x: -x[0])
        out = []
        for _ in range(min(q, len(gains))):
            idx = int((rng.random() ** 3) * len(gains))
            out.append(gains.pop(idx)[1])
        return out

    def destroy_related(seqs, q):
        pool = [t for _k, t in _all_tasks(seqs)]
        if not pool:
            return []
        seed_t = rng.choice(pool)
        sn = inst.client_node[seed_t.client_id]

        def rel(t):
            d = inst.D[sn][inst.client_node[t.client_id]]
            tw = 0 if (t.urgent or seed_t.urgent) else abs(t.early_min - seed_t.early_min) / 30.0
            return d + tw

        pool.sort(key=rel)
        return pool[:min(q, len(pool))]

    def _best_in_route(task, k, seqs, rc):
        """task 插入第 k 辆车各位置的最小近似成本增量 → (delta, pos)。"""
        s_ = seqs[k]
        best = None
        for pos in range(len(s_) + 1):
            d = route_cost(inst, s_[:pos] + [task] + s_[pos:], price)[0] - rc[k]
            if best is None or d < best[0]:
                best = (d, pos)
        return best

    def _repair(seqs, removed, regret):
        """greedy（regret=False）与 regret-2（regret=True）共用：对每个待插任务缓存"各车最佳插入"，
        插入后只重算被改动那一辆车，速度比逐轮全量重算快一个量级。"""
        seqs = [list(s) for s in seqs]
        rc = route_costs(inst, seqs, price)
        left = list(removed)
        if not regret:
            rng.shuffle(left)
        table = {id(t): [_best_in_route(t, k, seqs, rc) for k in range(len(seqs))] for t in left}
        while left:
            if regret:
                pick = None
                for t in left:
                    opts = sorted(((d, k, pos) for k, (d, pos) in enumerate(table[id(t)])), key=lambda x: (x[0], x[1]))
                    r = opts[1][0] - opts[0][0] if len(opts) > 1 else 0.0
                    if pick is None or r > pick[0]:
                        pick = (r, t, opts[0])
                _r, t, (_d, k, pos) = pick
            else:
                t = left[0]
                _d, k, pos = min(((d, k, pos) for k, (d, pos) in enumerate(table[id(t)])), key=lambda x: (x[0], x[1]))
            seqs[k].insert(pos, t)
            left.remove(t)
            del table[id(t)]
            rc[k] = route_cost(inst, seqs[k], price)[0]
            for u in left:
                table[id(u)][k] = _best_in_route(u, k, seqs, rc)
        return seqs

    def repair_greedy(seqs, removed):
        return _repair(seqs, removed, False)

    def repair_regret(seqs, removed):
        return _repair(seqs, removed, True)

    destroys = [("random", destroy_random), ("worst", destroy_worst), ("related", destroy_related)]
    repairs = [("greedy", repair_greedy), ("regret2", repair_regret)]
    dw = [1.0] * len(destroys)
    rw = [1.0] * len(repairs)
    dscore = [0.0] * len(destroys); dcount = [0] * len(destroys)
    rscore = [0.0] * len(repairs); rcount = [0] * len(repairs)
    usage = {"destroy": {n: 0 for n, _ in destroys}, "repair": {n: 0 for n, _ in repairs}}

    T0, T1 = 0.003 * cur_cost, 0.0001 * cur_cost   # 经 3 种温度×3 个种子×20 秒的小实验选定（0.01/0.003/0.001 起点，0.003 平均最好）
    it = 0
    q_lo, q_hi = 3, max(4, int(0.15 * n_tasks))

    def elapsed():
        return time.time() - t_start

    while True:
        if cancel is not None and cancel.is_set():
            break
        if max_iter is not None and it >= max_iter:
            break
        if max_iter is None and budget_s is not None and elapsed() >= budget_s:
            break
        it += 1
        if progress is not None and it % 25 == 0:
            progress(elapsed(), best_cost, it)
        di = rng.choices(range(len(destroys)), weights=dw)[0]
        ri = rng.choices(range(len(repairs)), weights=rw)[0]
        q = rng.randint(q_lo, q_hi)
        removed = destroys[di][1](cur, q)
        if not removed:
            continue
        partial = _remove(cur, removed)
        cand = repairs[ri][1](partial, removed)
        res = execute(inst, cand, price)
        usage["destroy"][destroys[di][0]] += 1
        usage["repair"][repairs[ri][0]] += 1
        dcount[di] += 1; rcount[ri] += 1
        score = 0.0
        if res is not None:
            c = res["cost"]["total"]
            if budget_s is not None and max_iter is None:
                frac = min(1.0, elapsed() / budget_s)
            else:
                frac = min(1.0, it / max_iter) if max_iter else 0.0
            T = T0 * (T1 / T0) ** frac
            if c < cur_cost - 1e-9:
                score = 9.0
            if c < cur_cost or rng.random() < math.exp(-(c - cur_cost) / max(T, 1e-9)):
                if score == 0.0:
                    score = 3.0
                cur, cur_cost = cand, c
            if c < best_cost - 1e-9:
                best, best_cost = [list(s) for s in cand], c
                score = 33.0
                trace.append((round(elapsed(), 3), best_cost))
        dscore[di] += score; rscore[ri] += score
        if it % 100 == 0:       # 每 100 次迭代按近期表现更新算子权重
            for i in range(len(destroys)):
                if dcount[i]:
                    dw[i] = 0.9 * dw[i] + 0.1 * (dscore[i] / dcount[i])
                dscore[i] = 0.0; dcount[i] = 0
            for i in range(len(repairs)):
                if rcount[i]:
                    rw[i] = 0.9 * rw[i] + 0.1 * (rscore[i] / rcount[i])
                rscore[i] = 0.0; rcount[i] = 0
            dw = [max(w, 0.05) for w in dw]; rw = [max(w, 0.05) for w in rw]

    # 收尾：对最优解做一次局部改进（relocate/swap），ALNS 擅长跳出局部最优，局部改进擅长把它压到底
    polished, pcost, _n = improve(inst, best, price, budget_s=5.0 if max_iter is None else None)
    if pcost < best_cost - 1e-9:
        best, best_cost = polished, pcost
    trace.append((round(elapsed(), 3), best_cost))
    return finalize(inst, best, price, "M3", {
        "trace": trace,
        "extra": {"iterations": it, "start_cost": first["cost"]["total"], "operator_usage": usage,
                  "runtime_s": elapsed(), "seed": seed},
    })
