# -*- coding: utf-8 -*-
"""真实道路几何：读取 build_sg_network.py 保存的每对节点之间的道路路线（polyline6），供轨迹与前端回放沿真实道路行驶。

节点编号：0=枢纽，1..n=客户点，其后=挂车场（与 Instance 的节点编号一致）。几何按**有序点对**存储（单行线使 i→j 与 j→i 走的路不同）。
"""
import gzip
import json
from functools import lru_cache
from pathlib import Path
from typing import List, Tuple

ROOT = Path(__file__).resolve().parent.parent
COMPANY = ROOT / "data" / "company"


def decode_polyline(s: str, precision: int = 6) -> List[Tuple[float, float]]:
    """Google 编码折线解码，返回 [(经度, 纬度), ...]（注意顺序为 经度,纬度，与坐标 x,y 一致）。"""
    factor = 10.0 ** precision
    lat = lon = 0
    i, out = 0, []
    while i < len(s):
        for axis in (0, 1):
            shift = result = 0
            while True:
                b = ord(s[i]) - 63
                i += 1
                result |= (b & 0x1F) << shift
                shift += 5
                if b < 0x20:
                    break
            delta = ~(result >> 1) if result & 1 else result >> 1
            if axis == 0:
                lat += delta
            else:
                lon += delta
        out.append((lon / factor, lat / factor))
    return out


def encode_polyline(points: List[Tuple[float, float]], precision: int = 6) -> str:
    """decode 的逆运算（测试用）。points 为 (经度, 纬度)。"""
    factor = 10 ** precision
    out, plat, plon = [], 0, 0
    for lon, lat in points:
        la, lo = int(round(lat * factor)), int(round(lon * factor))
        for v in (la - plat, lo - plon):
            v = ~(v << 1) if v < 0 else (v << 1)
            while v >= 0x20:
                out.append(chr((0x20 | (v & 0x1F)) + 63))
                v >>= 5
            out.append(chr(v + 63))
        plat, plon = la, lo
    return "".join(out)


@lru_cache(maxsize=4)
def load_geometry(company: str = "bluewave") -> dict:
    p = COMPANY / company / "geometry.json.gz"
    with gzip.open(p, "rt", encoding="utf-8") as f:
        return json.load(f)


def leg_geometry(i: int, j: int, company: str = "bluewave") -> List[Tuple[float, float]]:
    """节点 i → j 沿真实道路的折线（经度,纬度）。i==j 返回空。"""
    if i == j:
        return []
    g = load_geometry(company)
    return decode_polyline(g["pairs"][f"{i}-{j}"], g["precision"])
