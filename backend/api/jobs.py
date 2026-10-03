# -*- coding: utf-8 -*-
"""作业与运行存储：求解是异步作业，有进度、可取消；结果落盘后不可变；L1 在读取时由 L2 × 单价表计算。"""
import json
import os
import platform
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict
from pathlib import Path
from typing import Dict, Optional

from .. import datasets
from ..costs import PriceTable, cost_breakdown
from ..solvers.common import InfeasibleError
from ..solvers.m0r import solve_m0r, solve_m1
from ..solvers.m2_local import solve_m2
from ..solvers.m3_alns import solve_m3
from ..solvers.manual_sim import solve_manual
from ..verifier import verify

ROOT = Path(__file__).resolve().parent.parent.parent
RUNS = Path(os.environ.get("OUTPUT_DIR", ROOT / "outputs")) / "runs"
RECORDED = ROOT / "data" / "recorded_runs"      # 预先录好的演示运行（随仓库提交；线上重启后仍在，打开即可回放）
MAX_JOBS = int(os.environ.get("MAX_CONCURRENT_JOBS", "2"))
DEFAULT_BUDGET = float(os.environ.get("DEFAULT_BUDGET_S", "60"))
MAX_BUDGET = float(os.environ.get("MAX_BUDGET_S", "600"))

# 方法注册表：id → (族, 是否确定性, 口径, 适用时限)
METHODS = {
    "H0": {"family": "manual-mock", "deterministic": True, "inventory_mode": "realistic", "horizon": "none"},
    "M0-R": {"family": "heuristic", "deterministic": True, "inventory_mode": "realistic", "horizon": "seconds"},
    "M1": {"family": "heuristic", "deterministic": True, "inventory_mode": "realistic", "horizon": "seconds"},
    "M2": {"family": "heuristic", "deterministic": True, "inventory_mode": "realistic", "horizon": "seconds"},
    "M3": {"family": "metaheuristic", "deterministic": False, "inventory_mode": "realistic", "horizon": "minutes"},
}
MODES = {"now": "M2", "tomorrow": "M3"}      # 业务功能 → 方法（"立即排程"=M2，"明日排程"=M3）

_pool = ThreadPoolExecutor(max_workers=MAX_JOBS)
_jobs: Dict[str, dict] = {}
_cancel: Dict[str, threading.Event] = {}
_lock = threading.Lock()


def hardware() -> str:
    return f"{platform.system()} {platform.machine()} / {os.cpu_count()} cores / Python {platform.python_version()}"


def new_run_id() -> str:
    return time.strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:6]


def l2_of(res: dict) -> dict:
    d = res["cost"]["drivers"]
    return {"km": d["km"], "driver_minutes": d["driver_hours"] * 60.0, "tractors_owned": d["tractors_owned"],
            "tractors_used": d["tractors_used"], "trailers_total": d["trailers_total"],
            "penalty_minutes": d["penalty_minutes"], "unfinished": d["unfinished"]}


def l1_of(l2: dict, price: PriceTable) -> dict:
    return cost_breakdown(l2["km"], l2["driver_minutes"], l2["tractors_owned"], l2["tractors_used"], l2["trailers_total"],
                          l2["penalty_minutes"], l2["unfinished"], price)


def violation_codes(violations):
    """校验器的违反信息 → 代码（API 不返回自然语言，前端按当前语言渲染）。"""
    table = {"C1": "C1_TASK_ASSIGNMENT", "C3": "C3_RETURN_AFTER_HORIZON", "C4": "C4_INVENTORY_NEGATIVE"}
    out = []
    for v in violations:
        head = v.split(" ", 1)[0]
        out.append({"code": table.get(head, "VIOLATION"), "detail": v})
    return out


def _solve(method: str, inst, price: PriceTable, budget_s: Optional[float], seed: int, progress, cancel):
    if method == "H0":
        return solve_manual(inst, price)
    if method == "M0-R":
        return solve_m0r(inst, price)
    if method == "M1":
        return solve_m1(inst, price)
    if method == "M2":
        return solve_m2(inst, price, budget_s=budget_s or 30.0)
    if method == "M3":
        return solve_m3(inst, price, budget_s=budget_s or DEFAULT_BUDGET, seed=seed, progress=progress, cancel=cancel)
    raise ValueError(method)


def _job_main(run_id: str, req: dict, price: PriceTable):
    job = _jobs[run_id]
    cancel = _cancel[run_id]
    t0 = time.time()
    job["status"] = "RUNNING"
    try:
        inst = datasets.load(req["instance"], req["dataset"], {"tractor_count": req["tractors"]} if req.get("tractors") else None)
        method = req["method"]
        info = METHODS[method]

        def progress(elapsed, best, it):
            job["progress"] = {"elapsed_s": round(elapsed, 1), "best_cost": round(best, 1), "iterations": it}

        res = _solve(method, inst, price, req.get("budget_s"), req.get("seed", 0), progress, cancel)
        mode = info["inventory_mode"]
        rep = verify(inst, res["plan"], inventory_mode="enforce")
        status = "CANCELLED" if cancel.is_set() else "DONE"
        if not rep["feasible"]:
            status = "INVALID"
        l2 = l2_of(res) if "cost" in res else {
            "km": res["totals"]["mileage_km"], "driver_minutes": sum(res.get("end_times", [0])), "tractors_owned": inst.tractor_count,
            "tractors_used": rep["tractors_used"], "trailers_total": sum(t["trailers"] for t in inst.tcs),
            "penalty_minutes": res["totals"]["total_penalty"], "unfinished": res["totals"]["unfinished"]}
        record = {
            "run_id": run_id, "method": method, "dataset": req["dataset"], "instance": req["instance"],
            "mode": req.get("mode"), "inventory_mode": mode, "seed": req.get("seed", 0), "budget_s": req.get("budget_s"),
            "tractors": inst.tractor_count, "status": status, "runtime_s": round(time.time() - t0, 3), "hardware": hardware(),
            "created_at": time.strftime("%Y-%m-%dT%H:%M:%S"), "plan": res["plan"], "totals": res["totals"], "l2": l2,
            "trace": res.get("trace"), "extra": res.get("extra"),
            "verified": {"feasible": rep["feasible"], "violations": violation_codes(rep["violations"]),
                         "on_time_rate": rep["on_time_rate"], "unfinished": rep["unfinished"], "mileage_km": rep["mileage_km"],
                         "early_penalty": rep["early_penalty"], "late_penalty": rep["late_penalty"],
                         "tractors_used": rep["tractors_used"], "inventory_audit": rep["inventory_audit"]},
            "company": inst.meta.get("network"),
        }
        d = RUNS / run_id
        tmp = RUNS / (run_id + ".tmp")
        tmp.mkdir(parents=True, exist_ok=True)
        (tmp / "run.json").write_text(json.dumps(record, ensure_ascii=False), encoding="utf-8")
        tmp.rename(d)                                           # 目录写完再原子发布
        job.update({"status": status, "record": record})
    except InfeasibleError as e:
        job.update({"status": "INFEASIBLE", "error": {"code": "INFEASIBLE_NO_TRAILER", "detail": str(e)}})
    except Exception as e:  # noqa: BLE001
        job.update({"status": "ERROR", "error": {"code": "SOLVER_ERROR", "detail": f"{type(e).__name__}: {e}"}})


def submit(req: dict, price: PriceTable) -> str:
    run_id = new_run_id()
    with _lock:
        _jobs[run_id] = {"status": "QUEUED", "request": req}
        _cancel[run_id] = threading.Event()
    _pool.submit(_job_main, run_id, req, price)
    return run_id


_compare_jobs: Dict[str, dict] = {}


def submit_compare(name: str, dataset: str, budget_s: float, seeds: int) -> str:
    """用户输入新场景后，现场出"不甩挂 / 甩挂人工 / 立即排程 / 明日排程"的对比（后台作业，几十秒）。"""
    from ..compare import run_comparison
    cid = "cmp-" + new_run_id()
    _compare_jobs[cid] = {"status": "QUEUED", "instance": name, "dataset": dataset, "stage": None}

    def work():
        job = _compare_jobs[cid]
        job["status"] = "RUNNING"
        try:
            out = run_comparison(name, dataset, None, budget_s, seeds, m2_budget_s=20.0, progress=lambda s: job.__setitem__("stage", s))
            job.update({"status": "DONE", "tractors": out["tractors"]})
        except Exception as e:  # noqa: BLE001
            job.update({"status": "ERROR", "error": {"code": "SOLVER_ERROR", "detail": f"{type(e).__name__}: {e}"}})
    _pool.submit(work)
    return cid


def get_compare_job(cid: str) -> Optional[dict]:
    return _compare_jobs.get(cid)


def get_job(run_id: str) -> Optional[dict]:
    if run_id in _jobs:
        return _jobs[run_id]
    for base in (RUNS, RECORDED):
        p = base / run_id / "run.json"
        if p.exists():
            rec = json.loads(p.read_text(encoding="utf-8"))
            return {"status": rec["status"], "record": rec}
    return None


def list_recorded(dataset: Optional[str] = None) -> list:
    """预录运行的摘要列表（不含 plan）。"""
    out = []
    for p in sorted(RECORDED.glob("*/run.json")) if RECORDED.exists() else []:
        if p.parent.name.startswith("._"):
            continue
        r = json.loads(p.read_text(encoding="utf-8"))
        if dataset and r.get("dataset") != dataset:
            continue
        out.append({"run_id": r["run_id"], "instance": r["instance"], "dataset": r["dataset"], "method": r["method"],
                    "mode": r.get("mode"), "runtime_s": r.get("runtime_s"), "recorded": True})
    return out


def cancel(run_id: str) -> bool:
    ev = _cancel.get(run_id)
    if ev is None:
        return False
    ev.set()
    return True
