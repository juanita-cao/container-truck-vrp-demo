# -*- coding: utf-8 -*-
"""M0-R / M1 / M2 / M3 共用的小工具。所有方法只输出"每辆车的任务序列"，最终由 engine.execute 重放并整理。"""
from typing import List

from ..costs import PriceTable
from ..engine import execute, route_cost
from ..models import Instance, Task


class InfeasibleError(Exception):
    """现实口径下无法排程（取挂车时没有任何 TC 在该时刻有空挂）。"""


def finalize(inst: Instance, seqs: List[List[Task]], price: PriceTable, method: str, extra: dict = None) -> dict:
    res = execute(inst, seqs, price)
    if res is None:
        raise InfeasibleError("序列在现实口径下无法排程")
    res["method"] = method
    if extra:
        res.update(extra)
    return res


def route_costs(inst: Instance, seqs: List[List[Task]], price: PriceTable) -> List[float]:
    return [route_cost(inst, s, price)[0] if s else 0.0 for s in seqs]


def insertion_options(inst: Instance, seqs: List[List[Task]], rc: List[float], task: Task, price: PriceTable):
    """把 task 插入各车各位置的近似成本增量，升序返回 [(delta, k, pos)]。空车只在位置 0。"""
    opts = []
    for k, s in enumerate(seqs):
        base = rc[k]
        for pos in range(len(s) + 1):
            cand = s[:pos] + [task] + s[pos:]
            delta = route_cost(inst, cand, price)[0] - base
            opts.append((delta, k, pos))
    opts.sort(key=lambda x: (x[0], x[1], x[2]))
    return opts
