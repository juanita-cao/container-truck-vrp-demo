# -*- coding: utf-8 -*-
"""录制演示运行：一周七天 × （立即排程 M2 / 明日排程 M3）→ data/recorded_runs/rec-<算例>-<mode>/run.json（随仓库提交）。
线上服务重启会清空现场运行记录；录好的运行打开即可看计划与回放（轨迹在读取时由计划展开，与校验器一致）。
用法：python scripts/record_demo_runs.py [M3预算秒，默认60]"""
import json
import shutil
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from fastapi.testclient import TestClient  # noqa: E402

from backend.api import jobs  # noqa: E402
from backend.api.main import app  # noqa: E402

DAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]


def main():
    budget = float(sys.argv[1]) if len(sys.argv) > 1 else 60.0
    c = TestClient(app)
    out = ROOT / "data" / "recorded_runs"
    for day in DAYS:
        for mode, body in (("now", {}), ("tomorrow", {"budget_s": budget, "seed": 0})):
            name = f"sg_{day}"
            t0 = time.time()
            rid = c.post("/api/solve", json={"dataset": "demo_sg", "instance": name, "mode": mode, **body}).json()["run_id"]
            while True:
                s = c.get(f"/api/runs/{rid}").json()
                if s["status"] not in ("QUEUED", "RUNNING"):
                    break
                time.sleep(1)
            assert s["status"] == "DONE" and s["verified"]["feasible"], (name, mode, s["status"])
            rec = json.loads((jobs.RUNS / rid / "run.json").read_text(encoding="utf-8"))
            rec["run_id"] = f"rec-{name}-{mode}"
            rec["recorded"] = True
            d = out / rec["run_id"]
            d.mkdir(parents=True, exist_ok=True)
            (d / "run.json").write_text(json.dumps(rec, ensure_ascii=False), encoding="utf-8")
            shutil.rmtree(jobs.RUNS / rid, ignore_errors=True)
            print(f"{name} {mode}: cost={s['cost']['total']:.0f} {s['currency']} ({time.time() - t0:.0f}s)", flush=True)


if __name__ == "__main__":
    main()
