# -*- coding: utf-8 -*-
"""小切片：从完整算例里按种子抽出 n 个任务、指定牵引车数、TC 库存给足，用于精确法"尺子"与规模梯度。"""
import random
from typing import Optional

from .models import Instance


def make_slice(inst: Instance, n: int, seed: int = 0, tractors: Optional[int] = None, stock_per_tc: int = 50) -> Instance:
    rng = random.Random(seed)
    chosen = sorted(rng.sample(range(len(inst.tasks)), min(n, len(inst.tasks))))
    tasks = [inst.tasks[i] for i in chosen]
    tcs = [dict(t, trailers=stock_per_tc) for t in inst.tcs]
    k = tractors if tractors is not None else max(2, -(-n // 4))
    return Instance(id=f"{inst.id}__slice{n}_s{seed}", name=f"{inst.name} 切片 n={n} seed={seed}",
                    horizon_min=inst.horizon_min, speed_kmh=inst.speed_kmh, handling_min=inst.handling_min,
                    dc=inst.dc, tractor_count=k, clients=inst.clients, tcs=tcs, tasks=tasks,
                    meta={**inst.meta, "slice_of": inst.id, "n": n, "seed": seed},
                    coord_system=inst.coord_system, distance_matrix=inst.distance_matrix)
