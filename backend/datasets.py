# -*- coding: utf-8 -*-
"""数据集接口：数据集 = 一个坐标系 + 一组算例 + 距离矩阵；求解/校验/对比代码不感知具体数据集。
当前只有 demo_sg（新加坡真实路网上的虚构公司）。切换：环境变量 DATASET 或调用时显式传 dataset=。"""
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

ROOT = Path(__file__).resolve().parent.parent
INSTANCES = ROOT / "data" / "instances"
SCENARIOS = ROOT / "data" / "scenarios"      # 用户在"订单与车队"页输入并保存的场景（按数据集分目录，文件名以 my_ 开头）


@dataclass(frozen=True)
class Dataset:
    key: str
    label: str
    coord_system: str            # "grid"（km 网格）| "wgs84"（经纬度）
    purpose: str
    basemap: Optional[dict]      # 前端底图配置；None 表示无底图（抽象网格）


DATASETS = {
    "demo_sg": Dataset(
        key="demo_sg", label="新加坡演示（虚构点位）", coord_system="wgs84",
        purpose="路演/求职演示；真实新加坡地图上的虚构公司与虚构点位",
        basemap={"engine": "maplibre", "center": [103.82, 1.35], "zoom": 10.4,
                 "attribution": "底图数据来源与署名由前端按所选底图服务的使用条款展示"},
    ),
}
DEFAULT_DATASET = "demo_sg"


def active_dataset(dataset: Optional[str] = None) -> Dataset:
    key = dataset or os.environ.get("DATASET") or DEFAULT_DATASET
    if key not in DATASETS:
        raise ValueError(f"未知数据集 {key!r}；可选：{sorted(DATASETS)}")
    return DATASETS[key]


def instance_dir(dataset: Optional[str] = None) -> Path:
    return INSTANCES / active_dataset(dataset).key


def scenario_dir(dataset: Optional[str] = None) -> Path:
    return SCENARIOS / active_dataset(dataset).key


def is_scenario(name: str) -> bool:
    return name.startswith("my_")


def instance_path(name: str, dataset: Optional[str] = None) -> Path:
    p = (scenario_dir(dataset) if is_scenario(name) else instance_dir(dataset)) / f"{name}.json"
    if not p.exists():
        raise FileNotFoundError(f"数据集 {active_dataset(dataset).key!r} 中没有算例 {name!r}（{p}）")
    return p


def list_instances(dataset: Optional[str] = None) -> List[str]:
    d = instance_dir(dataset)
    # 忽略 macOS 在外置盘上生成的 "._*" AppleDouble 隐藏文件
    base = sorted(p.stem for p in d.glob("*.json") if not p.name.startswith("._")) if d.exists() else []
    sd = scenario_dir(dataset)
    mine = sorted(p.stem for p in sd.glob("my_*.json") if not p.name.startswith("._")) if sd.exists() else []
    return base + mine


def load(name: str, dataset: Optional[str] = None, override: Optional[dict] = None):
    from .models import load_instance
    return load_instance(instance_path(name, dataset), override)


def describe() -> list:
    """给 API 的 GET /datasets：每个数据集的元信息与算例数。"""
    cur = active_dataset().key
    return [{"key": d.key, "label": d.label, "coord_system": d.coord_system, "purpose": d.purpose,
             "basemap": d.basemap, "instances": len(list_instances(d.key)), "active": d.key == cur}
            for d in DATASETS.values()]
