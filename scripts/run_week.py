# -*- coding: utf-8 -*-
"""一周七天的方法对比离线预跑：对每一天依次跑 M1 / M0-R / M2 / M3（多种子），结果存 outputs/comparison/demo_sg_<day>_K<k>.json，
并汇总成 outputs/comparison/week_summary.json（供"一周总览"页读取）。
用法：python scripts/run_week.py [M3预算秒] [种子数]
"""
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from backend.generators.sg_company import WEEK  # noqa: E402


def main():
    budget = sys.argv[1] if len(sys.argv) > 1 else "20"
    seeds = sys.argv[2] if len(sys.argv) > 2 else "3"
    summary = []
    for key, label, n, k, _cap, note in WEEK:
        name = f"sg_{key}"
        print(f"--- {label} {name} 任务 {n} 车 {k} ---", flush=True)
        subprocess.run([sys.executable, str(ROOT / "scripts" / "compare_methods.py"), name, str(k), budget, seeds, "demo_sg"],
                       check=True, cwd=str(ROOT))
        res = json.loads((ROOT / "outputs" / "comparison" / f"demo_sg_{name}_K{k}.json").read_text(encoding="utf-8"))
        summary.append({"day": key, "label": label, "tasks": n, "tractors": k, "note": note, "rows": res["rows"],
                        "m3_runs": [{k: v for k, v in r.items() if k != "trace"} for r in res["m3_runs"]],
                        "m3_cost_mean": res["m3_cost_mean"], "m3_cost_std": res["m3_cost_std"], "m3_budget_s": res["m3_budget_s"],
                        "price_version": res["price_version"], "min_tractors": res.get("min_tractors"),
                        "serve_all": res.get("serve_all")})
    (ROOT / "outputs" / "comparison" / "week_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=1), encoding="utf-8")
    print("已写入 outputs/comparison/week_summary.json")


if __name__ == "__main__":
    main()
