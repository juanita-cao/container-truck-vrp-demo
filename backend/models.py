# -*- coding: utf-8 -*-
"""实例与距离。节点编号沿用原实现的 locationList：0=DC，1..nc=客户点，nc+1..=TC。"""
import json
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

S_TYPES = ("SZ", "SK")   # 送箱：DC → 客户点，甩下后牵引车自由
Q_TYPES = ("QK", "QZ")   # 取箱：客户点 → DC，回 DC 才完成


def csharp_round2(x: float) -> float:
    """复刻 C# Math.Round(d, 2)：按 100 缩放后取偶数舍入再缩回。"""
    return round(x * 100.0) / 100.0


@dataclass
class Task:
    id: int                      # M 编号（原实现 taskNum）
    client_id: int
    type: str
    early_min: Optional[int]     # 紧急任务无时间窗
    late_min: Optional[int]
    urgent: bool = False
    sub: int = 0                 # 子任务序号（taskCount>1 时 1..n，否则 0）
    job: Optional[int] = None    # 成对的单：同一个客户点的 送箱 + 取箱 共用一个 job 编号
    service_min: Optional[int] = None   # 该单客户装/卸一个箱子所需分钟数（不可分离模式下牵引车要在客户处等这么久）

    @property
    def label(self) -> str:
        return f"M{self.id}" + (f"-{self.sub}" if self.sub else "")


@dataclass
class Instance:
    id: str
    name: str
    horizon_min: int
    speed_kmh: int
    handling_min: int
    dc: tuple
    tractor_count: int
    clients: list
    tcs: list                    # [{id,x,y,trailers}]
    tasks: List[Task]            # 已按 taskCount 展开为子任务
    meta: dict = field(default_factory=dict)
    coord_system: str = "grid"   # "grid"：x,y 为 km 网格坐标；"wgs84"：x,y 为 经度,纬度（展示用）
    distance_matrix: Optional[list] = None   # 给定则直接使用（km，节点顺序同 0=DC,1..nc=客户点,其后 TC）；否则按 x,y 欧氏距离计算

    def __post_init__(self):
        self.nc = len(self.clients)
        self.ntc = len(self.tcs)
        pts = [self.dc] + [(c["x"], c["y"]) for c in self.clients] + [(t["x"], t["y"]) for t in self.tcs]
        n = len(pts)
        self.pts = pts
        if self.distance_matrix is not None:
            if len(self.distance_matrix) != n or any(len(r) != n for r in self.distance_matrix):
                raise ValueError(f"distance_matrix 维度应为 {n}×{n}")
            self.D = [[float(v) for v in row] for row in self.distance_matrix]
        else:
            if self.coord_system != "grid":
                raise ValueError("非网格坐标系必须提供 distance_matrix")
            self.D = [[0.0] * n for _ in range(n)]
            for i in range(n):
                for j in range(i + 1, n):
                    d = math.sqrt((pts[i][0] - pts[j][0]) ** 2 + (pts[i][1] - pts[j][1]) ** 2)
                    self.D[i][j] = self.D[j][i] = csharp_round2(d)
        self.client_node = {c["id"]: 1 + k for k, c in enumerate(self.clients)}
        self.tc_node = {t["id"]: 1 + self.nc + k for k, t in enumerate(self.tcs)}
        self.tc_first = 1 + self.nc          # 第一个 TC 的节点号

    def tc_nodes(self):
        return range(self.tc_first, self.tc_first + self.ntc)

    def minutes(self, dist: float) -> int:
        """路程 → 分钟：与原实现 (int)Math.Round(d/speed*60) 一致。"""
        return int(round(dist / self.speed_kmh * 60))


def load_instance(path, override: Optional[dict] = None) -> Instance:
    """override: tractor_count / tc_trailers（int 或 list：对所有 TC 或逐个覆盖）。"""
    d = json.loads(Path(path).read_text(encoding="utf-8"))
    override = override or {}
    tcs = [dict(t) for t in d["trailer_centers"]]
    if "tc_trailers" in override:
        v = override["tc_trailers"]
        for k, t in enumerate(tcs):
            t["trailers"] = v[k] if isinstance(v, list) and len(v) == len(tcs) else (v[0] if isinstance(v, list) else v)
    tasks: List[Task] = []
    for t in d["tasks"]:
        cnt = t.get("count", 1)
        if cnt > 1:
            for s in range(1, cnt + 1):
                tasks.append(Task(t["id"], t["client_id"], t["type"], t["early_min"], t["late_min"], t["urgent"], s, t.get("job"), t.get("service_min")))
        else:
            tasks.append(Task(t["id"], t["client_id"], t["type"], t["early_min"], t["late_min"], t["urgent"], 0, t.get("job"), t.get("service_min")))
    return Instance(
        id=d["id"], name=d["name"], horizon_min=d["horizon_min"], speed_kmh=d["speed_kmh"],
        handling_min=d["handling_min"], dc=(d["dc"]["x"], d["dc"]["y"]),
        tractor_count=override.get("tractor_count", d["tractor_count"]),
        clients=d["clients"], tcs=tcs, tasks=tasks, meta=d.get("meta", {}),
        coord_system=d.get("coord_system", "grid"), distance_matrix=d.get("distance_matrix_km"),
    )
