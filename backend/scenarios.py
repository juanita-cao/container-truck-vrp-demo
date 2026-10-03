# -*- coding: utf-8 -*-
"""场景（用户输入）：把"订单 + 车队"这组输入校验后生成一个算例（成对的单），保存为 data/scenarios/<数据集>/my_*.json。

输入的组成：
  订单（每天都要输入）：客户点、进口/出口、送箱时间窗、客户装/卸时间；  车队与资源：出勤牵引车数、每个挂车场的挂车数、平均车速。
  网络（枢纽、挂车场、客户点位置与道路距离）是主数据，这里只读；单价表在"单价表"页。
所有校验错误以 {code, 参数} 返回，界面按当前语言渲染。
"""
import json
import re
import time
from pathlib import Path
from typing import Dict, List, Optional

from . import datasets

HORIZON = 720
LIMITS = {"jobs": (1, 150), "tractors": (1, 60), "tc_stock": (0, 100), "speed": (10, 90), "service": (15, 600), "pickup_width": (15, 240)}


class ScenarioError(Exception):
    def __init__(self, errors: List[dict]):
        super().__init__("; ".join(e["code"] for e in errors))
        self.errors = errors


def jobs_of_instance(raw: dict) -> dict:
    """把算例里成对的任务还原成可编辑的"单"列表（用于预填"从某一天复制"）。"""
    by: Dict[int, Dict[str, dict]] = {}
    for t in raw["tasks"]:
        if t.get("job") is None:
            raise ScenarioError([{"code": "INSTANCE_NOT_PAIRED"}])
        by.setdefault(t["job"], {})["S" if t["type"] in ("SZ", "SK") else "Q"] = t
    jobs = []
    for j in sorted(by):
        s, q = by[j]["S"], by[j]["Q"]
        jobs.append({"client_id": s["client_id"], "kind": "import" if s["type"] == "SZ" else "export",
                     "delivery_early": s["early_min"], "delivery_late": s["late_min"], "service_min": s["service_min"],
                     "pickup_width": q["late_min"] - q["early_min"]})
    return {"tractors": raw["tractor_count"], "tc_stock": [t["trailers"] for t in raw["trailer_centers"]],
            "speed_kmh": raw["speed_kmh"], "jobs": jobs}


def _validate(base: dict, payload: dict) -> List[dict]:
    errs: List[dict] = []
    n_tc = len(base["trailer_centers"])
    cids = {c["id"] for c in base["clients"]}
    lo, hi = LIMITS["tractors"]
    if not isinstance(payload.get("tractors"), int) or not lo <= payload["tractors"] <= hi:
        errs.append({"code": "TRACTORS_OUT_OF_RANGE", "min": lo, "max": hi})
    stock = payload.get("tc_stock")
    lo, hi = LIMITS["tc_stock"]
    if not isinstance(stock, list) or len(stock) != n_tc or any(not isinstance(x, int) or not lo <= x <= hi for x in stock):
        errs.append({"code": "TC_STOCK_INVALID", "yards": n_tc, "min": lo, "max": hi})
    lo, hi = LIMITS["speed"]
    if not isinstance(payload.get("speed_kmh"), int) or not lo <= payload["speed_kmh"] <= hi:
        errs.append({"code": "SPEED_OUT_OF_RANGE", "min": lo, "max": hi})
    jobs = payload.get("jobs")
    lo, hi = LIMITS["jobs"]
    if not isinstance(jobs, list) or not lo <= len(jobs) <= hi:
        errs.append({"code": "JOB_COUNT_OUT_OF_RANGE", "min": lo, "max": hi})
        return errs
    for i, j in enumerate(jobs, start=1):
        def bad(code, **kw):
            errs.append({"code": code, "job": i, **kw})
        if j.get("client_id") not in cids:
            bad("JOB_CLIENT_UNKNOWN")
        if j.get("kind") not in ("import", "export"):
            bad("JOB_KIND_INVALID")
        e, l, sv, pw = j.get("delivery_early"), j.get("delivery_late"), j.get("service_min"), j.get("pickup_width", 90)
        if not all(isinstance(x, int) for x in (e, l, sv, pw)):
            bad("JOB_TIME_INVALID")
            continue
        if not (0 <= e < l <= HORIZON):
            bad("JOB_DELIVERY_WINDOW_INVALID", horizon=HORIZON)
        if not LIMITS["service"][0] <= sv <= LIMITS["service"][1]:
            bad("JOB_SERVICE_OUT_OF_RANGE", min=LIMITS["service"][0], max=LIMITS["service"][1])
        if not LIMITS["pickup_width"][0] <= pw <= LIMITS["pickup_width"][1]:
            bad("JOB_PICKUP_WIDTH_OUT_OF_RANGE", min=LIMITS["pickup_width"][0], max=LIMITS["pickup_width"][1])
        if isinstance(e, int) and isinstance(sv, int) and e + sv > HORIZON:
            bad("JOB_PICKUP_AFTER_HORIZON", horizon=HORIZON)       # 取箱最早开始 = 送箱最早开始 + 客户处理时间，不能超出工作日
    return errs


def build_instance(base: dict, name: str, label: str, payload: dict, base_name: Optional[str] = None) -> dict:
    errs = _validate(base, payload)
    if errs:
        raise ScenarioError(errs)
    tasks = []
    for j, jb in enumerate(payload["jobs"], start=1):
        s_type, q_type = ("SZ", "QK") if jb["kind"] == "import" else ("SK", "QZ")
        pw = jb.get("pickup_width", 90)
        tasks.append({"id": 2 * j - 1, "client_id": jb["client_id"], "type": s_type, "early_min": jb["delivery_early"],
                      "late_min": jb["delivery_late"], "urgent": False, "count": 1, "job": j, "service_min": jb["service_min"]})
        qe = jb["delivery_early"] + jb["service_min"]
        tasks.append({"id": 2 * j, "client_id": jb["client_id"], "type": q_type, "early_min": qe, "late_min": qe + pw,
                      "urgent": False, "count": 1, "job": j, "service_min": jb["service_min"]})
    inst = json.loads(json.dumps(base))          # 深拷贝：网络（客户点、挂车场、距离矩阵）沿用，只改订单与车队
    inst.update({"id": name, "name": label, "source": "scenario", "tractor_count": payload["tractors"],
                 "speed_kmh": payload["speed_kmh"], "tasks": tasks})
    for tc, n in zip(inst["trailer_centers"], payload["tc_stock"]):
        tc["trailers"] = n
    meta = dict(inst.get("meta", {}))
    for k in ("day", "day_label", "day_note", "week", "weekly_pattern_note"):
        meta.pop(k, None)
    meta.update({"scenario": True, "label": label, "base": base_name, "paired_jobs": len(payload["jobs"]),
                 "created_at": time.strftime("%Y-%m-%dT%H:%M:%S"), "fictional": True})
    inst["meta"] = meta
    return inst


def slugify(label: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "_", label.lower()).strip("_")
    return s[:30] or time.strftime("%Y%m%d_%H%M%S")


def save(inst: dict, dataset: str) -> Path:
    d = datasets.scenario_dir(dataset)
    d.mkdir(parents=True, exist_ok=True)
    p = d / f"{inst['id']}.json"
    tmp = d / f".{inst['id']}.tmp"
    tmp.write_text(json.dumps(inst, ensure_ascii=False), encoding="utf-8")
    tmp.replace(p)
    return p


def delete(name: str, dataset: str) -> bool:
    if not datasets.is_scenario(name):
        return False
    p = datasets.scenario_dir(dataset) / f"{name}.json"
    if p.exists():
        p.unlink()
        return True
    return False
