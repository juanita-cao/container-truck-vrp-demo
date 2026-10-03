# -*- coding: utf-8 -*-
"""独立校验器。

只吃 Instance + Plan，不依赖任何求解器代码：重放每辆车的任务序列，算出每个任务的开始/完成时刻、里程、
早到/迟到，检查硬约束，并按"现实口径"审计 TC 挂车库存（按真实时间顺序重放取/还事件）。

时间/路径语义取自既有规则与原实现，四舍五入规则与原实现一致。

Plan 格式：
    {"tractors": [[{"task": "M21", "tc": 2}, ...], ...],   # tc=转场用到的 TC id（取/还挂车），不需要时为 None
     "unfinished": ["M5", ...]}
"""
from typing import Dict, List

from .models import Instance, Q_TYPES, S_TYPES


def _nearest_tc_any(inst: Instance, from_node: int, to_node: int) -> int:
    """argmin D[from,tc]+D[tc,to]，平局取先出现者（与原实现严格 '>' 比较一致）。"""
    best, best_tc = None, None
    for tc in inst.tc_nodes():
        d = inst.D[from_node][tc] + inst.D[tc][to_node]
        if best is None or best > d:
            best, best_tc = d, tc
    return best_tc


def verify(inst: Instance, plan: dict, check_inventory: bool = True, inventory_mode: str = "audit") -> dict:
    """inventory_mode: "audit" = 旧口径（库存违反只报告，不算不可行）；"enforce" = 现实口径（按真实时间库存为负 → 违反 C4）。"""
    H, sp = inst.horizon_min, inst.speed_kmh
    hand = inst.handling_min
    D = inst.D
    by_label = {t.label: t for t in inst.tasks}
    violations: List[str] = []
    tasks_out: Dict[str, dict] = {}
    tractors_out = []
    events = []  # (time, +1/-1, tc_node, tractor, label)
    seen = set()

    for k, entries in enumerate(plan["tractors"]):
        cur = None        # 上一个任务：(task, finish_time)
        t_mileage = 0.0
        end_time = 0
        for e in entries:
            task = by_label[e["task"]]
            if task.label in seen:
                violations.append(f"C1 任务 {task.label} 被重复安排")
            seen.add(task.label)
            cn = inst.client_node[task.client_id]
            tc = inst.tc_node[e["tc"]] if e.get("tc") is not None else None
            ev_tc_time = None

            def need_tc():
                if tc is None:
                    violations.append(f"K{k+1} 任务 {task.label} 的转场需要 TC 但计划未给出")
                    raise ValueError("missing tc")

            try:
                if cur is None:
                    if task.type in S_TYPES:
                        need_tc()
                        dist = D[0][tc] + D[tc][0] + D[0][cn]
                        arrive = inst.minutes(dist) + hand
                        finish = arrive
                        events.append((inst.minutes(D[0][tc]), -1, tc, k, task.label))
                    else:
                        dist1 = D[0][cn]
                        arrive = inst.minutes(dist1)
                        dist = dist1 + D[cn][0]
                        finish = inst.minutes(dist)
                else:
                    ctask, cfin = cur
                    cc = inst.client_node[ctask.client_id]
                    if ctask.type in Q_TYPES:
                        if task.type in Q_TYPES:
                            need_tc()
                            d1 = D[0][tc] + D[tc][cn]
                            arrive = cfin + inst.minutes(d1) + hand
                            dist = d1 + D[cn][0]
                            finish = cfin + inst.minutes(dist) + hand
                            events.append((cfin + inst.minutes(D[0][tc]), +1, tc, k, task.label))
                        else:
                            dist = D[0][cn]
                            arrive = cfin + inst.minutes(dist) + hand * 2
                            finish = arrive
                    else:
                        if task.type in Q_TYPES:
                            d1 = D[cc][cn]
                            arrive = cfin + inst.minutes(d1)
                            dist = d1 + D[cn][0]
                            finish = cfin + inst.minutes(dist)
                        else:
                            need_tc()
                            dist = D[cc][tc] + D[tc][0] + D[0][cn]
                            arrive = cfin + inst.minutes(dist) + hand
                            finish = arrive
                            events.append((cfin + inst.minutes(D[cc][tc]), -1, tc, k, task.label))
            except ValueError:
                break

            early = late = 0
            if not task.urgent:
                early = max(task.early_min - arrive, 0)
                late = max(arrive - task.late_min, 0)
            tasks_out[task.label] = {
                "tractor": k + 1, "type": task.type, "client": task.client_id, "start": arrive, "finish": finish,
                "mileage": dist, "early": early, "late": late,
                "in_window": (not task.urgent) and early == 0 and late == 0,
            }
            t_mileage += dist
            cur = (task, finish)
            end_time = finish

        # 当天最后返回 DC（旧口径：送箱→直接回；取箱→先还空挂到最近 TC 再回）
        back_dist = 0.0
        if cur is not None:
            ctask, cfin = cur
            cc = inst.client_node[ctask.client_id]
            if ctask.type in S_TYPES:
                back_dist = D[cc][0]
                end_time = cfin + inst.minutes(back_dist)
            else:
                tcn = _nearest_tc_any(inst, 0, 0)
                back_dist = D[0][tcn] + D[tcn][0]
                end_time = cfin + inst.minutes(back_dist) + hand
                events.append((cfin + inst.minutes(D[0][tcn]), +1, tcn, k, ctask.label + "_final"))
            if end_time > H:
                violations.append(f"C3 K{k+1} 回到 DC 的时刻 {end_time} 超过规划期 {H}")
        t_mileage += back_dist
        tractors_out.append({"tractor": k + 1, "tasks": len(entries), "mileage": t_mileage,
                             "end_time": end_time if entries else 0})

    for lab in plan.get("unfinished", []):
        if lab in seen:
            violations.append(f"C1 任务 {lab} 同时出现在已安排与未完成清单")
    missing = set(by_label) - seen - set(plan.get("unfinished", []))
    if missing:
        violations.append(f"C1 有 {len(missing)} 个任务既未安排也未列入未完成清单：{sorted(missing)[:5]}…")

    audit = _inventory_audit(inst, events) if (check_inventory or inventory_mode == "enforce") else None
    if inventory_mode == "enforce" and audit and audit["negative_events"]:
        violations.append(f"C4 现实口径下 TC 库存出现负值 {audit['negative_events']} 次，例：{audit['examples'][:2]}")
    total_early = sum(v["early"] for v in tasks_out.values())
    total_late = sum(v["late"] for v in tasks_out.values())
    return {
        "unfinished": len(set(plan.get("unfinished", []))),
        "mileage_km": round(sum(t["mileage"] for t in tractors_out), 2),
        "early_penalty": total_early, "late_penalty": total_late,
        "total_penalty": total_early + total_late,
        "on_time_rate": (sum(1 for v in tasks_out.values() if v["in_window"]) / len(tasks_out)) if tasks_out else None,
        "tractors_used": sum(1 for t in tractors_out if t["tasks"]),
        "tasks": tasks_out, "tractors": tractors_out,
        "violations": violations, "feasible": not violations,
        "inventory_audit": audit,
    }


def _inventory_audit(inst: Instance, events) -> dict:
    """现实口径审计：按真实时间重放 TC 取(-1)/还(+1)事件；同一时刻先还后取。统计库存为负的次数。"""
    inv = {tc: inst.tcs[tc - inst.tc_first]["trailers"] for tc in inst.tc_nodes()}
    ev = sorted(events, key=lambda e: (e[0], -e[1]))
    negatives = []
    min_inv = dict(inv)
    for t, delta, tc, k, lab in ev:
        inv[tc] += delta
        if inv[tc] < min_inv[tc]:
            min_inv[tc] = inv[tc]
        if inv[tc] < 0:
            negatives.append({"time": t, "tc": tc - inst.tc_first + 1, "tractor": k + 1, "task": lab, "inventory": inv[tc]})
    return {"mode": "chronological", "negative_events": len(negatives), "examples": negatives[:5],
            "min_inventory": {tc - inst.tc_first + 1: v for tc, v in min_inv.items()}}
