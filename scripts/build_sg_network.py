# -*- coding: utf-8 -*-
"""构建虚构公司 Bluewave Drayage Co. 的新加坡真实路网网络。

输入：本地 OSRM 服务（OpenStreetMap 数据快照 + OSRM car 画像，开源、免费、本机运行，不访问任何在线服务）。
做的事：
  1. 在新加坡真实的工业区/港口物流集聚区一带抽样候选点，用 OSRM /nearest 吸附到真实道路；吸附距离 > 阈值的点视为"不在可通行陆地上"，丢弃重抽。
  2. 用 OSRM /table 一次性得到所有点之间的**真实道路距离**与自由流行驶时间矩阵。**保留方向**：单行线、立交会让 A→B 与 B→A 的道路不同（例如去程 2.5 km、回程要绕 12.6 km），矩阵不对称，计算引擎按方向使用。
  3. 用 OSRM /route 取每一个**有序点对**的真实道路路线几何（polyline6），存成压缩文件，前端回放时沿真实道路行驶。
输出：data/company/bluewave/network.json、data/company/bluewave/geometry.json.gz
注意：点位是虚构的（落在真实工业区的真实道路上，但不对应任何真实企业或地址）；OSM 数据使用需署名 © OpenStreetMap contributors（ODbL）。
用法：先启动本地 OSRM，再
    python scripts/build_sg_network.py [--osrm http://localhost:5000] [--write]
默认 dry-run：只做抽样与吸附并打印摘要，不写文件、不做几何；加 --write 才执行距离矩阵与几何并落盘。
"""
import argparse
import gzip
import json
import math
import random
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "company" / "bluewave"
SNAP_MAX_M = 250.0          # 吸附距离上限：超过说明原点不在道路可达的陆地上
OSM_SNAPSHOT = "geofabrik malaysia-singapore-brunei 2026-10-02"

# (区域名, 经度, 纬度, 权重, 抽样半径[度], 说明) —— 真实工业区/港口物流集聚区的近似中心；落点以"吸附到道路"为准
AREAS = [
    ("Pasir Panjang（港口旁）", 103.7850, 1.2800, 0.14, 0.012),
    ("Tuas", 103.6400, 1.3200, 0.14, 0.015),
    ("Jurong-Penjuru", 103.7150, 1.3200, 0.16, 0.014),
    ("Pandan-Clementi", 103.7500, 1.3150, 0.06, 0.008),
    ("Kallang-Paya Lebar", 103.8750, 1.3200, 0.08, 0.008),
    ("Defu-Ubi-Kaki Bukit", 103.8950, 1.3450, 0.10, 0.010),
    ("Tampines", 103.9400, 1.3550, 0.08, 0.008),
    ("Changi-Loyang", 103.9750, 1.3650, 0.08, 0.008),
    ("Sungei Kadut-Kranji", 103.7550, 1.4150, 0.08, 0.008),
    ("Woodlands", 103.7900, 1.4400, 0.08, 0.008),
]
HUB_SEED = ("Bluewave Hub（虚构，近 Pasir Panjang 港口）", 103.7850, 1.2790)
TC_SEEDS = [("Tuas 挂车场", 103.6450, 1.3180), ("Jurong 挂车场", 103.7150, 1.3250),
            ("Pasir Panjang 挂车场", 103.7900, 1.2820), ("Defu 挂车场", 103.8950, 1.3500),
            ("Sungei Kadut 挂车场", 103.7550, 1.4120)]


def get(url, retries=3):
    for k in range(retries):
        try:
            with urllib.request.urlopen(url, timeout=60) as r:
                return json.loads(r.read().decode("utf-8"))
        except Exception:
            if k == retries - 1:
                raise
            time.sleep(1)


def snap(osrm, lon, lat):
    d = get(f"{osrm}/nearest/v1/driving/{lon},{lat}?number=1")
    w = d["waypoints"][0]
    return w["location"][0], w["location"][1], w["distance"]


def snap_near(osrm, lon, lat, rng, radius, tries=60):
    """围绕 (lon,lat) 抽样并吸附，直到吸附距离达标。返回 (lon,lat,吸附距离m,尝试次数)。"""
    for k in range(1, tries + 1):
        r = radius * math.sqrt(rng.random())
        th = rng.random() * 2 * math.pi
        x = lon + r * math.cos(th) / math.cos(math.radians(lat))
        y = lat + r * math.sin(th)
        sx, sy, dist = snap(osrm, round(x, 6), round(y, 6))
        if dist <= SNAP_MAX_M:
            return round(sx, 6), round(sy, 6), dist, k
    raise RuntimeError(f"在 ({lon},{lat}) 附近 {tries} 次抽样都吸附不到道路")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--osrm", default="http://localhost:5000")
    ap.add_argument("--clients", type=int, default=80)
    ap.add_argument("--seed", type=int, default=2026)
    ap.add_argument("--write", action="store_true")
    a = ap.parse_args()
    rng = random.Random(a.seed)

    # 1. 点位：枢纽、TC、客户点（都吸附到真实道路）
    hub = snap_near(a.osrm, HUB_SEED[1], HUB_SEED[2], rng, 0.004)
    tcs = [snap_near(a.osrm, lon, lat, rng, 0.004) + (nm,) for nm, lon, lat in TC_SEEDS]
    weights = [x[3] for x in AREAS]
    clients, attempts = [], 0
    for i in range(a.clients):
        area = rng.choices(AREAS, weights=weights)[0]
        lon, lat, dist, k = snap_near(a.osrm, area[1], area[2], rng, area[4])
        attempts += k
        clients.append({"id": i + 1, "x": lon, "y": lat, "name": f"客户 SG-{i + 1:03d}（虚构）", "area": area[0],
                        "snap_m": round(dist, 1)})
    by_area = {}
    for c in clients:
        by_area[c["area"]] = by_area.get(c["area"], 0) + 1
    print(f"点位：枢纽 1、挂车场 {len(tcs)}、客户点 {len(clients)}；抽样共尝试 {attempts} 次（接受率 {len(clients) / attempts:.0%}）")
    print("客户点按区域：", by_area)
    print(f"吸附距离 均值 {sum(c['snap_m'] for c in clients) / len(clients):.0f} m，最大 {max(c['snap_m'] for c in clients):.0f} m（上限 {SNAP_MAX_M:.0f} m）")
    if not a.write:
        print("dry-run：未做矩阵与几何，未写文件（加 --write 执行）")
        return

    pts = [(hub[0], hub[1])] + [(c["x"], c["y"]) for c in clients] + [(t[0], t[1]) for t in tcs]
    N = len(pts)

    # 2. 路网距离/时间矩阵
    coords = ";".join(f"{x},{y}" for x, y in pts)
    tab = get(f"{a.osrm}/table/v1/driving/{coords}?annotations=distance,duration")
    dist_m, dur_s = tab["distances"], tab["durations"]
    if any(v is None for row in dist_m for v in row):
        raise RuntimeError("路网矩阵里有不可达的点对")
    D = [[round(dist_m[i][j] / 1000.0, 2) for j in range(N)] for i in range(N)]
    T = [[round(dur_s[i][j] / 60.0, 2) for j in range(N)] for i in range(N)]
    asym = [abs(dist_m[i][j] - dist_m[j][i]) / max(min(dist_m[i][j], dist_m[j][i]), 1) for i in range(N) for j in range(i + 1, N)]
    asym_sorted = sorted(asym)
    free_speed = sum(D[i][j] for i in range(N) for j in range(N) if i != j) / (sum(T[i][j] for i in range(N) for j in range(N) if i != j) / 60.0)
    print(f"矩阵 {N}×{N}（有方向）；单行线造成的两方向距离差：中位 {asym_sorted[len(asym) // 2]:.1%}，90 分位 {asym_sorted[int(len(asym) * 0.9)]:.1%}，最大 {max(asym):.0%}")
    print(f"OSRM 自由流平均车速 {free_speed:.0f} km/h（本项目按拥堵/货车/装卸折算用更低的平均车速，见数据集元数据）")

    # 3. 真实道路几何（每个有序点对一条，因为单行线使 i→j 与 j→i 走的路不同）
    pairs = {}
    t0 = time.time()
    for i in range(N):
        for j in range(N):
            if i == j:
                continue
            r = get(f"{a.osrm}/route/v1/driving/{pts[i][0]},{pts[i][1]};{pts[j][0]},{pts[j][1]}?overview=full&geometries=polyline6&steps=false")
            pairs[f"{i}-{j}"] = r["routes"][0]["geometry"]
    print(f"几何：{len(pairs)} 条真实道路路线，用时 {time.time() - t0:.0f}s")

    OUT.mkdir(parents=True, exist_ok=True)
    net = {
        "company": "Bluewave Drayage Co.（虚构）", "coord_system": "wgs84", "fictional": True,
        "osm_snapshot": OSM_SNAPSHOT, "routing": "OSRM car 画像（本地）", "attribution": "© OpenStreetMap contributors",
        "snap_max_m": SNAP_MAX_M, "seed": a.seed,
        "hub": {"x": hub[0], "y": hub[1], "name": HUB_SEED[0], "snap_m": round(hub[2], 1)},
        "trailer_centers": [{"id": i + 1, "x": t[0], "y": t[1], "name": t[4], "snap_m": round(t[2], 1)} for i, t in enumerate(tcs)],   # t = (经度, 纬度, 吸附距离, 尝试次数, 名称)
        "clients": clients,
        "distance_matrix_km": D, "duration_matrix_min_free_flow": T,
        "matrix_note": "路网距离，保留方向（D[i][j] 为 i→j 的真实道路距离）；节点顺序 0=枢纽、1..n=客户点、其后=挂车场",
        "geometry_file": "geometry.json.gz", "osrm_free_flow_speed_kmh": round(free_speed, 1),
    }
    (OUT / "network.json").write_text(json.dumps(net, ensure_ascii=False, indent=1), encoding="utf-8")
    with gzip.open(OUT / "geometry.json.gz", "wt", encoding="utf-8") as f:
        json.dump({"precision": 6, "directed": True, "node_order": "0=枢纽,1..n=客户点,其后=挂车场", "pairs": pairs}, f)
    print("已写入", OUT)


if __name__ == "__main__":
    main()
