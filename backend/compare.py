# -*- coding: utf-8 -*-
"""多方法对比（现实口径）：不甩挂 C0 / 甩挂人工 H0 / M1 / M0-R / M2 / M3，同一算例、同一单价表。
离线预跑脚本 scripts/compare_methods.py 与 API 的"现场出对比"（用户输入新场景之后）共用这一份逻辑，结果文件格式相同。
"""
import json
import statistics
import time
from pathlib import Path
from typing import Callable, Optional

from . import datasets
from .conventional import solve_conventional
from .costs import default_price_table
from .solvers.m0r import solve_m0r, solve_m1
from .solvers.m2_local import solve_m2
from .solvers.m3_alns import solve_m3
from .solvers.manual_sim import solve_manual
from .verifier import verify

ROOT = Path(__file__).resolve().parent.parent


def _l2(c):
    d = c["drivers"]
    return {"km": d["km"], "driver_minutes": d["driver_hours"] * 60.0, "tractors_owned": d["tractors_owned"],
            "tractors_used": d["tractors_used"], "trailers_total": d["trailers_total"],
            "penalty_minutes": d["penalty_minutes"], "unfinished": d["unfinished"]}


def row(inst, res, dt):
    rep = verify(inst, res["plan"], inventory_mode="enforce")
    c = res["cost"]
    return {"method": res["method"], "cost": round(c["total"], 1), "fuel": round(c["fuel"], 1), "driver": round(c["driver"], 1),
            "penalty": round(c["penalty"], 1), "outsource": round(c["outsource"], 1),
            "km": res["totals"]["mileage_km"], "unfinished": res["totals"]["unfinished"],
            "penalty_min": res["totals"]["total_penalty"], "on_time_rate": rep["on_time_rate"],
            "feasible": rep["feasible"], "runtime_s": round(dt, 2), "l2": _l2(c)}


def row_conventional(inst, res, dt):
    c = res["cost"]
    return {"method": "C0", "cost": round(c["total"], 1), "fuel": round(c["fuel"], 1), "driver": round(c["driver"], 1),
            "penalty": round(c["penalty"], 1), "outsource": round(c["outsource"], 1), "km": res["totals"]["mileage_km"],
            "unfinished": res["totals"]["unfinished"], "penalty_min": res["totals"]["total_penalty"], "on_time_rate": res["on_time_rate"],
            "feasible": True, "runtime_s": round(dt, 2), "wait_hours": round(res["wait_hours"], 1), "l2": _l2(c)}


def min_fleet(name, dataset, fn, kmax=80):
    """最少需要几辆牵引车才能全部完成（不外包）。规则类方法很快，直接逐辆扫描。"""
    for k in range(1, kmax + 1):
        try:
            if fn(datasets.load(name, dataset, {"tractor_count": k}))["totals"]["unfinished"] == 0:
                return k
        except Exception:  # noqa: BLE001
            continue
    return None


def run_comparison(name: str, dataset: str, k: Optional[int] = None, budget_s: float = 30.0, seeds: int = 3,
                   m2_budget_s: float = 60.0, progress: Optional[Callable[[str], None]] = None, write: bool = True) -> dict:
    say = progress or (lambda msg: None)
    inst = datasets.load(name, dataset, {"tractor_count": k} if k else None)
    k = inst.tractor_count
    price = default_price_table(dataset)
    out = {"dataset": dataset, "instance": name, "tractors": k, "price_version": price.version, "inventory_mode": "realistic",
           "currency": price.currency, "m3_budget_s": budget_s, "rows": [], "m3_runs": []}
    paired = all(t.job is not None for t in inst.tasks)
    if paired:
        say("conventional")
        t = time.time(); rc = solve_conventional(inst, price); out["rows"].append(row_conventional(inst, rc, time.time() - t))
        say("fleet")
        out["min_tractors"] = {"C0": min_fleet(name, dataset, lambda i: solve_conventional(i, price)),
                               "H0": min_fleet(name, dataset, lambda i: solve_manual(i, price)),
                               "M0-R": min_fleet(name, dataset, lambda i: solve_m0r(i, price))}
        mt = out["min_tractors"]
        if mt["C0"] and mt["H0"]:
            say("serve_all")
            serve = {}
            for m, kk, fn in (("C0", mt["C0"], lambda i: solve_conventional(i, price)), ("H0", mt["H0"], lambda i: solve_manual(i, price)),
                              ("M2", mt["H0"], lambda i: solve_m2(i, price, budget_s=min(30.0, m2_budget_s))),
                              ("M3", mt["H0"], lambda i: solve_m3(i, price, budget_s=budget_s, seed=1))):
                ik = datasets.load(name, dataset, {"tractor_count": kk})
                t = time.time(); rk = fn(ik); dtk = time.time() - t
                rw = row_conventional(ik, rk, dtk) if m == "C0" else row(ik, rk, dtk)
                rw["tractors"] = kk
                serve[m] = rw
            out["serve_all"] = serve
    say("drop_pull_rules")
    for fn in (solve_manual, solve_m1, solve_m0r):
        t = time.time(); r = fn(inst, price); out["rows"].append(row(inst, r, time.time() - t))
    say("m2")
    t = time.time(); r2 = solve_m2(inst, price, budget_s=m2_budget_s); out["rows"].append(row(inst, r2, time.time() - t))
    say("m3")
    costs = []
    for seed in range(1, seeds + 1):
        t = time.time(); r3 = solve_m3(inst, price, budget_s=budget_s, seed=seed); dt = time.time() - t
        rr = row(inst, r3, dt); rr["seed"] = seed; out["m3_runs"].append({**rr, "trace": r3["trace"]})
        costs.append(rr["cost"])
    out["m3_cost_mean"] = round(statistics.mean(costs), 1)
    out["m3_cost_std"] = round(statistics.pstdev(costs), 1)
    if write:
        d = ROOT / "outputs" / "comparison"
        d.mkdir(parents=True, exist_ok=True)
        (d / (f"{dataset}_{name}_K{k}.json")).write_text(
            json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    return out
