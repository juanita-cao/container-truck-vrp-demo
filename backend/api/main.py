# -*- coding: utf-8 -*-
"""FastAPI 后端。启动：uvicorn backend.api.main:app --port 8000

约定：所有接口前缀 /api；数据集用查询参数 dataset=（缺省取环境变量 DATASET，再缺省 demo_sg）；接口只返回数据与代码，不返回自然语言（前端按当前语言渲染。
"""
import csv
import json
import os
from dataclasses import asdict
from pathlib import Path
from typing import List, Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from .. import datasets
from ..costs import PriceTable, default_price_table
from .. import scenarios
from ..trajectory import build_trajectory
from . import jobs

ROOT = Path(__file__).resolve().parent.parent.parent
OUT = Path(os.environ.get("OUTPUT_DIR", ROOT / "outputs"))
PRICE_DIR = ROOT / "data" / "price_tables"

app = FastAPI(title="Drayage Planner API", version="0.1")
app.add_middleware(CORSMiddleware, allow_origins=os.environ.get("CORS_ORIGINS", "http://localhost:5173").split(","),
                   allow_methods=["*"], allow_headers=["*"])


def err(http_status: int, code: str, **params):
    raise HTTPException(status_code=http_status, detail={"code": code, "params": params})


# ---------------- 单价表（按数据集存放；带版本；修改产生新版本，不覆盖） ----------------
_prices: dict = {}      # dataset -> {version: PriceTable}
_current: dict = {}     # dataset -> 当前版本


def _store(ds: str) -> dict:
    if ds not in _prices:
        _prices[ds] = {"v1": default_price_table(ds)}
        _current[ds] = "v1"
    return _prices[ds]


class PriceIn(BaseModel):
    fuel_l_per_100km: float = Field(ge=0)
    fuel_price_per_l: float = Field(ge=0)
    driver_per_hour: float = Field(ge=0)
    tractor_fixed_per_day: float = Field(ge=0)
    trailer_fixed_per_day: float = Field(ge=0)
    outsource_per_task: float = Field(ge=0)
    penalty_per_minute: float = Field(ge=0)
    currency: str = "CNY"


def price_of(version: Optional[str], ds: Optional[str] = None) -> PriceTable:
    ds = ds or datasets.active_dataset().key
    store = _store(ds)
    v = version or _current[ds]
    if v not in store:
        err(404, "PRICE_VERSION_NOT_FOUND", version=v)
    return store[v]


@app.get("/api/price-table")
def get_price_table(version: Optional[str] = None, dataset: Optional[str] = None):
    ds = _ds(dataset)
    p = price_of(version, ds)
    return {**p.to_dict(), "current": _current[ds], "versions": sorted(_store(ds)), "dataset": ds}


@app.put("/api/price-table")
def put_price_table(body: PriceIn, dataset: Optional[str] = None):
    ds = _ds(dataset)
    store = _store(ds)
    prev = store[_current[ds]]
    p = PriceTable(**body.model_dump(), version=f"v{len(store) + 1}")
    p.sources = {k: ("edited" if getattr(p, k) != getattr(prev, k) else prev.sources.get(k, "fictional")) for k in p.sources}
    store[p.version] = p
    _current[ds] = p.version
    return {**p.to_dict(), "current": p.version, "versions": sorted(store), "dataset": ds}


# ---------------- 基础信息 ----------------
@app.get("/api/health")
def health():
    return {"status": "ok", "version": app.version, "dataset_default": datasets.active_dataset().key, "hardware": jobs.hardware()}


@app.get("/api/datasets")
def get_datasets():
    return datasets.describe()


def _ds(dataset: Optional[str]) -> str:
    try:
        return datasets.active_dataset(dataset).key
    except ValueError:
        err(400, "UNKNOWN_DATASET", dataset=dataset)


@app.get("/api/instances")
def list_instances(dataset: Optional[str] = None):
    ds = _ds(dataset)
    out = []
    week = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
    names = datasets.list_instances(ds)
    names.sort(key=lambda n: (1 if datasets.is_scenario(n) else 0, week.index(n[3:]) if n.startswith("sg_") and n[3:] in week else 99, n))   # 一周按周一到周日排序，用户场景排最后
    for name in names:
        raw = json.loads(datasets.instance_path(name, ds).read_text(encoding="utf-8"))
        out.append({"name": name, "dataset": ds, "tasks": sum(t.get("count", 1) for t in raw["tasks"]), "clients": len(raw["clients"]),
                    "tcs": len(raw["trailer_centers"]), "tractors": raw["tractor_count"],
                    "trailers": sum(t["trailers"] for t in raw["trailer_centers"]), "coord_system": raw.get("coord_system", "grid"),
                    "meta": {k: raw.get("meta", {}).get(k) for k in ("day", "day_label", "week", "day_note", "group", "fictional", "scenario", "label", "base")}})
    return out


@app.get("/api/instances/{name}")
def get_instance(name: str, dataset: Optional[str] = None, matrix: bool = True):
    ds = _ds(dataset)
    try:
        raw = json.loads(datasets.instance_path(name, ds).read_text(encoding="utf-8"))
    except FileNotFoundError:
        err(404, "INSTANCE_NOT_FOUND", instance=name, dataset=ds)
    if not matrix:
        raw.pop("distance_matrix_km", None)
    return raw


# ---------------- 输入：网络（只读）、场景（订单与车队） ----------------
AREA_EN = {"Pasir Panjang（港口旁）": "Pasir Panjang (near port)"}
YARD_EN = {"Tuas 挂车场": "Tuas yard", "Jurong 挂车场": "Jurong yard", "Pasir Panjang 挂车场": "Pasir Panjang yard",
           "Defu 挂车场": "Defu yard", "Sungei Kadut 挂车场": "Sungei Kadut yard"}
NETWORK_DIR = ROOT / "data" / "company" / "bluewave"


@app.get("/api/network")
def get_network(dataset: Optional[str] = None):
    """订单输入页用的主数据（只读）：枢纽、挂车场、客户点。名称带中英文（专有地名以英文为主）。"""
    ds = _ds(dataset)
    p = NETWORK_DIR / "network.json"
    if ds != "demo_sg" or not p.exists():
        err(404, "NO_NETWORK_FOR_DATASET", dataset=ds)
    net = json.loads(p.read_text(encoding="utf-8"))
    return {
        "company": "Bluewave Drayage Co.", "fictional": True, "attribution": net["attribution"],
        "hub": {"x": net["hub"]["x"], "y": net["hub"]["y"], "name_en": "Bluewave Hub (fictional, near Pasir Panjang port)", "name_zh": net["hub"]["name"]},
        "yards": [{"id": t["id"], "x": t["x"], "y": t["y"], "name_en": YARD_EN.get(t["name"], t["name"]), "name_zh": t["name"]} for t in net["trailer_centers"]],
        "clients": [{"id": c["id"], "x": c["x"], "y": c["y"], "code": f"SG-{c['id']:03d}", "area": AREA_EN.get(c["area"], c["area"])} for c in net["clients"]],
        "horizon_min": scenarios.HORIZON, "limits": {k: list(v) for k, v in scenarios.LIMITS.items()},
        "defaults": {"speed_kmh": 35, "handling_min": 30, "service_range_min": [60, 360], "pickup_width_min": 90},
    }


@app.get("/api/instances/{name}/jobs")
def get_instance_jobs(name: str, dataset: Optional[str] = None):
    """把某一天（或某个已保存场景）还原成可编辑的订单与车队，用于"从某一天复制"。"""
    ds = _ds(dataset)
    try:
        raw = json.loads(datasets.instance_path(name, ds).read_text(encoding="utf-8"))
    except FileNotFoundError:
        err(404, "INSTANCE_NOT_FOUND", instance=name, dataset=ds)
    try:
        v = scenarios.jobs_of_instance(raw)
    except scenarios.ScenarioError as e:
        err(409, "SCENARIO_INVALID", errors=e.errors)
    return {"name": name, "label": raw.get("meta", {}).get("label") or raw.get("name"), **v}


class ScenarioIn(BaseModel):
    base: str = Field(description="沿用其网络（客户点/挂车场/距离）的算例，如 sg_mon")
    label: str = Field(min_length=1, max_length=60)
    tractors: int
    tc_stock: List[int]
    speed_kmh: int
    jobs: List[dict]


def _scenario_instance(body: ScenarioIn, ds: str, name: str) -> dict:
    try:
        base = json.loads(datasets.instance_path(body.base if not datasets.is_scenario(body.base) else "sg_mon", ds).read_text(encoding="utf-8"))
    except FileNotFoundError:
        err(404, "INSTANCE_NOT_FOUND", instance=body.base, dataset=ds)
    try:
        return scenarios.build_instance(base, name, body.label, body.model_dump(exclude={"base", "label"}), body.base)
    except scenarios.ScenarioError as e:
        err(422, "SCENARIO_INVALID", errors=e.errors)


def _summary(inst: dict) -> dict:
    return {"name": inst["id"], "label": inst["name"], "tasks": len(inst["tasks"]), "jobs": len(inst["tasks"]) // 2, "tractors": inst["tractor_count"]}


@app.post("/api/scenarios", status_code=201)
def create_scenario(body: ScenarioIn, dataset: Optional[str] = None):
    ds = _ds(dataset)
    if ds != "demo_sg":
        err(404, "NO_NETWORK_FOR_DATASET", dataset=ds)
    existing = set(datasets.list_instances(ds))
    name = f"my_{scenarios.slugify(body.label)}"
    n = 2
    while name in existing:
        name = f"my_{scenarios.slugify(body.label)}_{n}"
        n += 1
    inst = _scenario_instance(body, ds, name)
    scenarios.save(inst, ds)
    return _summary(inst)


@app.put("/api/scenarios/{name}")
def update_scenario(name: str, body: ScenarioIn, dataset: Optional[str] = None):
    ds = _ds(dataset)
    if not datasets.is_scenario(name) or name not in datasets.list_instances(ds):
        err(404, "INSTANCE_NOT_FOUND", instance=name, dataset=ds)
    inst = _scenario_instance(body, ds, name)
    scenarios.save(inst, ds)
    return _summary(inst)


@app.delete("/api/scenarios/{name}")
def delete_scenario(name: str, dataset: Optional[str] = None):
    ds = _ds(dataset)
    if not datasets.is_scenario(name) or not scenarios.delete(name, ds):
        err(404, "INSTANCE_NOT_FOUND", instance=name, dataset=ds)
    return {"deleted": name}


class CompareRunIn(BaseModel):
    dataset: Optional[str] = None
    instance: str
    budget_s: float = Field(default=10.0, gt=0, le=60)
    seeds: int = Field(default=1, ge=1, le=3)


@app.post("/api/compare/run", status_code=202)
def run_compare(body: CompareRunIn):
    """现场出对比：不甩挂 / 甩挂人工 / 立即排程 / 明日排程（后台作业，约几十秒）。完成后 GET /api/compare 即可读到。"""
    ds = _ds(body.dataset)
    if body.instance not in datasets.list_instances(ds):
        err(404, "INSTANCE_NOT_FOUND", instance=body.instance, dataset=ds)
    return {"compare_job": jobs.submit_compare(body.instance, ds, body.budget_s, body.seeds)}


@app.get("/api/compare/jobs/{cid}")
def get_compare_job(cid: str):
    j = jobs.get_compare_job(cid)
    if j is None:
        err(404, "RUN_NOT_FOUND", run_id=cid)
    return {"compare_job": cid, **{k: v for k, v in j.items() if k != "request"}}


@app.get("/api/methods")
def get_methods():
    return [{"id": k, **v} for k, v in jobs.METHODS.items()] + [{"modes": jobs.MODES}]


# ---------------- 求解（异步作业） ----------------
class SolveIn(BaseModel):
    dataset: Optional[str] = None
    instance: str
    mode: Optional[str] = Field(default=None, description="now → M2；tomorrow → M3；缺省则必须给 method（高级）")
    method: Optional[str] = None
    budget_s: Optional[float] = Field(default=None, gt=0)
    seed: int = 0
    tractors: Optional[int] = Field(default=None, gt=0)
    price_version: Optional[str] = None


@app.post("/api/solve", status_code=202)
def solve(body: SolveIn):
    ds = _ds(body.dataset)
    method = body.method or jobs.MODES.get(body.mode or "")
    if method is None:
        err(400, "METHOD_OR_MODE_REQUIRED")
    if method not in jobs.METHODS:
        err(400, "UNKNOWN_METHOD", method=method)
    if body.instance not in datasets.list_instances(ds):
        err(404, "INSTANCE_NOT_FOUND", instance=body.instance, dataset=ds)
    budget = body.budget_s
    if budget is not None and budget > jobs.MAX_BUDGET:
        err(400, "BUDGET_TOO_LARGE", max=jobs.MAX_BUDGET)
    req = {"dataset": ds, "instance": body.instance, "mode": body.mode, "method": method, "budget_s": budget,
           "seed": body.seed, "tractors": body.tractors}
    run_id = jobs.submit(req, price_of(body.price_version, ds))
    return {"run_id": run_id, "method": method}


@app.get("/api/runs/{run_id}")
def get_run(run_id: str, price: Optional[str] = None):
    job = jobs.get_job(run_id)
    if job is None:
        err(404, "RUN_NOT_FOUND", run_id=run_id)
    st = job["status"]
    if "record" not in job:
        out = {"run_id": run_id, "status": st}
        if "progress" in job:
            out["progress"] = job["progress"]
        if "error" in job:
            out["error"] = job["error"]
        return out
    rec = dict(job["record"])
    p = price_of(price, rec["dataset"])
    rec["cost"] = jobs.l1_of(rec["l2"], p)
    rec["price_version"] = p.version
    rec["currency"] = p.currency
    return rec


@app.post("/api/runs/{run_id}/cancel")
def cancel_run(run_id: str):
    job = jobs.get_job(run_id)
    if job is None:
        err(404, "RUN_NOT_FOUND", run_id=run_id)
    if job["status"] not in ("QUEUED", "RUNNING"):
        err(409, "RUN_ALREADY_FINISHED", status=job["status"])
    jobs.cancel(run_id)
    return {"run_id": run_id, "status": "CANCEL_REQUESTED"}


@app.get("/api/runs/{run_id}/trajectory")
def get_trajectory(run_id: str):
    job = jobs.get_job(run_id)
    if job is None:
        err(404, "RUN_NOT_FOUND", run_id=run_id)
    if "record" not in job or job["status"] not in ("DONE", "CANCELLED"):
        err(409, "RUN_NOT_READY_OR_INVALID", status=job["status"])
    rec = job["record"]
    cache = jobs.RUNS / run_id / "trajectory.json"
    if cache.exists():
        return json.loads(cache.read_text(encoding="utf-8"))
    inst = datasets.load(rec["instance"], rec["dataset"], {"tractor_count": rec["tractors"]})
    tr = build_trajectory(inst, rec["plan"], rec.get("company"))
    tr["run_id"] = run_id
    try:
        cache.write_text(json.dumps(tr, ensure_ascii=False), encoding="utf-8")
    except OSError:
        pass
    return tr


# ---------------- 离线预跑结果（演示读取，不现场重跑） ----------------
def _read_json(p: Path):
    if not p.exists():
        return None
    return json.loads(p.read_text(encoding="utf-8"))


@app.get("/api/week")
def get_week(dataset: Optional[str] = None, price: Optional[str] = None):
    """一周七天：每天的任务量、出勤车、各方法日成本（金额按所选单价表由 L2 重算）与一周合计。"""
    ds = _ds(dataset)
    if ds != "demo_sg":
        err(404, "NO_WEEK_FOR_DATASET", dataset=ds)
    w = _read_json(OUT / "comparison" / "week_summary.json")
    if w is None:
        err(404, "WEEK_NOT_PRECOMPUTED")
    p = price_of(price, ds)
    days, totals = [], {}
    for d in w:
        rows = {r["method"]: r for r in d["rows"]}
        tot = lambda r: jobs.l1_of(r["l2"], p)["total"] if "l2" in r else r["cost"]
        m3c = [tot(x) for x in d.get("m3_runs", [])] or [d["m3_cost_mean"]]
        cost = {m: tot(r) for m, r in rows.items()}
        cost["M3"] = sum(m3c) / len(m3c)
        for m, c in cost.items():
            totals[m] = totals.get(m, 0.0) + c
        days.append({"day": d["day"], "label": d["label"], "tasks": d["tasks"], "tractors": d["tractors"], "note": d["note"],
                     "min_tractors": d.get("min_tractors"),
                     "cost": cost, "km": {m: r["km"] for m, r in rows.items()},
                     "on_time_rate": {m: r["on_time_rate"] for m, r in rows.items()}})
    serve_tot: dict = {}
    for d in w:
        for m, r in (d.get("serve_all") or {}).items():
            serve_tot[m] = serve_tot.get(m, 0.0) + (jobs.l1_of(r["l2"], p)["total"] if "l2" in r else r["cost"])
    h0 = totals["H0"]
    c0 = totals.get("C0")
    return {"price_version": p.version, "currency": p.currency, "days": days,
            "week_total": {m: {"cost": c, "vs_manual_pct": round((c / h0 - 1) * 100, 1),
                               "vs_traditional_pct": round((c / c0 - 1) * 100, 1) if c0 else None} for m, c in totals.items()},
            "serve_all_total": {m: {"cost": c, "vs_traditional_pct": round((c / serve_tot["C0"] - 1) * 100, 1)} for m, c in serve_tot.items()} if "C0" in serve_tot else None,
            "note": {"code": "WEEKLY_PATTERN_IS_ASSUMPTION"}}


@app.get("/api/compare")
def get_compare(instance: str, tractors: Optional[int] = None, dataset: Optional[str] = None, include_advanced: bool = False,
                price: Optional[str] = None):
    """默认三列：人工(H0)、立即排程(M2)、明日排程(M3)；include_advanced=true 才返回 M1 / M0-R。数字来自离线预跑，金额按所选单价表重算。"""
    ds = _ds(dataset)
    files = [f for f in (OUT / "comparison").glob(f"{'demo_sg_' if ds == 'demo_sg' else ''}{instance}_K{tractors or '*'}.json")
             if not f.name.startswith("._")]
    if not files:
        err(404, "COMPARISON_NOT_PRECOMPUTED", instance=instance)
    data = json.loads(max(files, key=lambda f: f.stat().st_mtime).read_text(encoding="utf-8"))   # 有多个车队规模的结果时取最新的
    p = price_of(price, ds)
    rows = {r["method"]: r for r in data["rows"]}
    m3 = [m for m in data["m3_runs"]]

    def total(r):          # 金额读取时按所选单价表由 L2 重算；旧结果没有 L2 时退回预跑时的金额（单价表 v1）
        return jobs.l1_of(r["l2"], p)["total"] if "l2" in r else r["cost"]

    def pack(method, r):
        out = {"method": method, "cost": total(r), "km": r["km"], "on_time_rate": r["on_time_rate"], "unfinished": r["unfinished"],
               "runtime_s": r["runtime_s"], "penalty_min": r["penalty_min"]}
        if "wait_hours" in r:
            out["wait_hours"] = r["wait_hours"]
        return out
    h0 = total(rows["H0"])
    c0 = total(rows["C0"]) if "C0" in rows else None
    m3_costs = [total(x) for x in m3]
    mean = sum(m3_costs) / len(m3_costs)
    std = (sum((c - mean) ** 2 for c in m3_costs) / len(m3_costs)) ** 0.5
    cols = ([pack("C0", rows["C0"])] if c0 is not None else []) + [pack("H0", rows["H0"]), pack("M2", rows["M2"]),
            {"method": "M3", "cost": mean, "cost_std": std, "budget_s": data["m3_budget_s"],
             "km": sum(x["km"] for x in m3) / len(m3), "on_time_rate": sum(x["on_time_rate"] for x in m3) / len(m3),
             "unfinished": max(x["unfinished"] for x in m3), "runtime_s": sum(x["runtime_s"] for x in m3) / len(m3),
             "seeds": len(m3), "trace": m3[0]["trace"]}]
    for c in cols:
        c["vs_manual_pct"] = round((c["cost"] / h0 - 1) * 100, 1)
        if c0 is not None:
            c["vs_traditional_pct"] = round((c["cost"] / c0 - 1) * 100, 1)
    serve = None
    if data.get("serve_all"):
        sa = data["serve_all"]
        base_cost = total(sa["C0"])
        serve = [{"method": m, "tractors": sa[m]["tractors"], "cost": total(sa[m]), "unfinished": sa[m]["unfinished"], "km": sa[m]["km"],
                  "vs_traditional_pct": round((total(sa[m]) / base_cost - 1) * 100, 1)} for m in ("C0", "H0", "M2", "M3") if m in sa]
    out = {"dataset": ds, "instance": instance, "tractors": data["tractors"], "inventory_mode": data["inventory_mode"],
           "price_version": data["price_version"], "currency": p.currency, "columns": cols,
           "min_tractors": data.get("min_tractors"), "serve_all": serve,
           "note": {"code": "H0_IS_SIMULATED_MANUAL"}}
    if include_advanced:
        out["advanced"] = [pack(m, rows[m]) for m in ("M0-R", "M1") if m in rows]
    return out


@app.get("/api/scaling")
def get_scaling():
    d = _read_json(OUT / "scaling" / "exact_scaling.json")
    if d is None:
        err(404, "SCALING_NOT_PRECOMPUTED")
    return d
