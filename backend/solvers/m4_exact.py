# -*- coding: utf-8 -*-
"""M4：小规模精确求解（CP-SAT）——当"尺子"，不用于日常。

模型：所有牵引车相同、从 DC 出发，所以是"多条回路经过 DC"的问题（AddMultipleCircuit），任务可被跳过（外包）。
相邻任务的转场时间/距离只取决于前后任务类型与位置（TC 取"最近者"，与既有规则一致），因此都是预先算好的常数；
到达时刻 = 前一任务完成时刻 + 转场耗时（旧口径无等待）；早到/迟到按分钟折算；目标 = 变动成本（燃油 + 司机 + 惩罚折算 + 外包）。
**松弛说明：** 本模型不考虑 TC 库存耦合（视作库存充足）。因此它给出的是"库存充足时"的最优值，同时是库存受限问题的有效下界；
若重放得到的计划在现实口径下可行（切片里 TC 库存给足时必然可行），它就是真正的最优。
"""
import os
import time
from typing import List, Optional

from ortools.sat.python import cp_model

from ..costs import PriceTable
from ..engine import Rec, Timeline, nearest_tc_return, plan_transition
from ..models import Instance, Q_TYPES, Task
from .common import InfeasibleError, finalize

SCALE = 100  # 成本单位 0.01 元


def _unlimited_timeline(inst: Instance) -> Timeline:
    tl = Timeline(inst)
    tl.init = {tc: 10 ** 6 for tc in inst.tc_nodes()}
    return tl


def transitions(inst: Instance, tasks: List[Task]):
    """预计算：first[j]=(到达,完成,距离)；pair[i][j]=(到达偏移,完成偏移,距离)；back[i]=(回程分钟,回程距离)。"""
    tl = _unlimited_timeline(inst)
    first, pair, back = [], [], []
    for t in tasks:
        a, f, d, _tc, _ev = plan_transition(inst, None, t, tl)
        first.append((a, f, d))
    for i, ti in enumerate(tasks):
        node = inst.client_node[ti.client_id]
        cur = Rec(ti, node)
        cur.finish = 0
        row = []
        for j, tj in enumerate(tasks):
            if i == j:
                row.append(None)
                continue
            a, f, d, _tc, _ev = plan_transition(inst, cur, tj, tl)
            row.append((a, f, d))
        pair.append(row)
        if ti.type in Q_TYPES:
            tcn = nearest_tc_return(inst, 0)
            bd = inst.D[0][tcn] + inst.D[tcn][0]
            back.append((inst.minutes(bd) + inst.handling_min, bd))
        else:
            bd = inst.D[node][0]
            back.append((inst.minutes(bd), bd))
    return first, pair, back


def solve_m4(inst: Instance, price: Optional[PriceTable] = None, budget_s: float = 60.0, workers: Optional[int] = None,
             seed: int = 0) -> dict:
    price = price or PriceTable()
    tasks = list(inst.tasks)
    n = len(tasks)
    H = inst.horizon_min
    HMAX = 3 * H
    K = inst.tractor_count
    first, pair, back = transitions(inst, tasks)

    fuel_unit = price.fuel_l_per_100km / 100.0 * price.fuel_price_per_l
    c_km = lambda d: int(round(d * fuel_unit * SCALE))
    c_drv = int(round(price.driver_per_hour / 60.0 * SCALE))
    c_pen = int(round(price.penalty_per_minute * SCALE))
    c_out = int(round(price.outsource_per_task * SCALE))

    m = cp_model.CpModel()
    arr = [m.NewIntVar(0, HMAX, f"arr{j}") for j in range(n)]
    fin = [m.NewIntVar(0, HMAX, f"fin{j}") for j in range(n)]
    early = [m.NewIntVar(0, HMAX, f"e{j}") for j in range(n)]
    late = [m.NewIntVar(0, HMAX, f"l{j}") for j in range(n)]
    end = [m.NewIntVar(0, HMAX, f"end{j}") for j in range(n)]
    skip = [m.NewBoolVar(f"skip{j}") for j in range(n)]
    arcs, obj = [], []

    lit0, lit_end = [], []
    for j in range(n):
        l = m.NewBoolVar(f"first{j}")
        lit0.append(l)
        arcs.append((0, j + 1, l))
        a0, f0, d0 = first[j]
        m.Add(arr[j] == a0).OnlyEnforceIf(l)
        m.Add(fin[j] == f0).OnlyEnforceIf(l)
        obj.append(c_km(d0) * l)
        le = m.NewBoolVar(f"last{j}")
        lit_end.append(le)
        arcs.append((j + 1, 0, le))
        bt, bd = back[j]
        m.Add(fin[j] + bt <= H).OnlyEnforceIf(le)       # 回 DC 不得晚于规划期
        m.Add(end[j] == fin[j] + bt).OnlyEnforceIf(le)
        m.Add(end[j] == 0).OnlyEnforceIf(le.Not())
        obj.append(c_km(bd) * le)
        obj.append(c_drv * end[j])
        arcs.append((j + 1, j + 1, skip[j]))            # 自环 = 该任务被跳过（外包）
        obj.append(c_out * skip[j])
    for i in range(n):
        for j in range(n):
            if i == j:
                continue
            l = m.NewBoolVar(f"a{i}_{j}")
            arcs.append((i + 1, j + 1, l))
            a, f, d = pair[i][j]
            m.Add(arr[j] == fin[i] + a).OnlyEnforceIf(l)
            m.Add(fin[j] == fin[i] + f).OnlyEnforceIf(l)
            obj.append(c_km(d) * l)
            pair[i][j] = pair[i][j] + (l,)
    m.AddMultipleCircuit(arcs)
    m.Add(sum(lit0) <= K)

    for j, t in enumerate(tasks):
        if not t.urgent:
            m.Add(early[j] >= t.early_min - arr[j]).OnlyEnforceIf(skip[j].Not())
            m.Add(late[j] >= arr[j] - t.late_min).OnlyEnforceIf(skip[j].Not())
        obj.append(c_pen * (early[j] + late[j]))
    m.Minimize(sum(obj))

    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = budget_s
    solver.parameters.num_workers = workers or min(8, os.cpu_count() or 4)
    solver.parameters.random_seed = seed
    t0 = time.time()
    status = solver.Solve(m)
    runtime = time.time() - t0
    name = solver.StatusName(status)
    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        raise InfeasibleError(f"CP-SAT 状态 {name}，未找到可行解")

    succ, starts = {}, []
    for j in range(n):
        if solver.Value(lit0[j]):
            starts.append(j)
    for i in range(n):
        for j in range(n):
            if i != j and solver.Value(pair[i][j][3]):
                succ[i] = j
    seqs: List[List[Task]] = []
    for s in starts:
        seq, cur = [], s
        while cur is not None:
            seq.append(tasks[cur])
            cur = succ.get(cur)
        seqs.append(seq)
    while len(seqs) < K:
        seqs.append([])

    obj_val = solver.ObjectiveValue() / SCALE
    bound = solver.BestObjectiveBound() / SCALE
    res = finalize(inst, seqs, price, "M4", {
        "extra": {"status": name, "objective_variable_cost": obj_val, "best_bound_variable_cost": bound,
                  "gap": (obj_val - bound) / obj_val if obj_val else 0.0, "runtime_s": runtime,
                  "proven_optimal": status == cp_model.OPTIMAL, "relaxation": "TC库存视为充足"},
    })
    return res


def variable_cost(res: dict) -> float:
    """L1 里随方案变化的部分（扣掉牵引车、挂车固定成本），用来和 CP-SAT 目标值核对。"""
    c = res["cost"]
    return c["total"] - c["tractor_fixed"] - c["trailer_fixed"]
