# -*- coding: utf-8 -*-
"""轨迹：把计划展开成逐车逐段的运动轨迹，供回放、库存时间线使用。

轨迹**与校验器逐项一致**（任务到达/完成时刻、各车回 DC 时刻、总里程），由测试保证；前端回放只播放这份数据，不自行推算。

时间分配规则（展示层的拆分，不改变任何数字）：旧口径只给出"整个转场的耗时 = 总路程取整 + 装卸时间"。
这里把总路程按各段距离比例拆成行驶段（累计取整，使行驶总分钟等于取整值），装卸时间作为停留段放在发生装卸的节点：
  送箱前（取空挂→回枢纽装箱）：停留在枢纽；取箱后再送箱（Q→S）：枢纽停留 2 次装卸；取箱后再取箱（Q→Q）：停留在挂车场（还挂车）。
挂车状态：none（只有牵引头）/ empty_trailer（拖空挂）/ loaded（挂重箱）/ empty_container（挂空箱）。
"""
from typing import Dict, List, Optional, Tuple

from .geometry import leg_geometry
from .models import Instance, Q_TYPES, S_TYPES
from .engine import nearest_tc_return


def _split(total_min: int, dists: List[float]) -> List[int]:
    """把 total_min 按 dists 的比例拆成整数分钟（累计取整，和恒等于 total_min）。"""
    s = sum(dists)
    if s <= 0:
        out = [0] * len(dists)
        if out:
            out[-1] = total_min
        return out
    out, acc_d, acc_m = [], 0.0, 0
    for d in dists:
        acc_d += d
        m = int(round(total_min * acc_d / s)) - acc_m
        out.append(m)
        acc_m += m
    out[-1] += total_min - acc_m
    return out


def build_trajectory(inst: Instance, plan: dict, company: Optional[str] = None) -> dict:
    D, hand, mins = inst.D, inst.handling_min, inst.minutes
    by_label = {t.label: t for t in inst.tasks}
    pts = inst.pts                                           # 节点坐标 (x,y)=(经度,纬度) 或网格 km
    use_roads = inst.coord_system == "wgs84" and company is not None
    inv_events: List[Tuple[int, int, int]] = []              # (时间, 增减, TC 节点)
    tractors, events, used_pairs = [], [], set()

    def node_xy(n):
        return pts[n]

    def seg(k, t0, t1, kind, a, b, trailer, task, km=0.0, note=None):
        s = {"t0": t0, "t1": t1, "kind": kind, "from": a, "to": b, "trailer": trailer, "task": task, "km": round(km, 4),
             "x0": node_xy(a)[0], "y0": node_xy(a)[1], "x1": node_xy(b)[0], "y1": node_xy(b)[1]}
        if kind == "travel" and use_roads and a != b:
            used_pairs.add((a, b))
        if note:
            s["note"] = note
        return s

    def ev(k, t, kind, node, task, **kw):
        e = {"t": t, "tractor": k + 1, "kind": kind, "node": node, "task": task}
        e.update(kw)
        events.append(e)

    for k, entries in enumerate(plan["tractors"]):
        segs: List[dict] = []
        cur = None   # (task, finish, node)
        t_end = 0
        for en in entries:
            task = by_label[en["task"]]
            cn = inst.client_node[task.client_id]
            tc = inst.tc_node[en["tc"]] if en.get("tc") is not None else None
            carry = "loaded" if task.type in ("SZ", "QZ") else "empty_container"
            lab = task.label
            if cur is None:
                if task.type in S_TYPES:
                    d = [D[0][tc], D[tc][0], D[0][cn]]
                    T = mins(sum(d))
                    m = _split(T, d)
                    t = 0
                    segs.append(seg(k, t, t + m[0], "travel", 0, tc, "none", lab, d[0])); t += m[0]
                    inv_events.append((t, -1, tc)); ev(k, t, "hook", tc, lab)
                    segs.append(seg(k, t, t + m[1], "travel", tc, 0, "empty_trailer", lab, d[1])); t += m[1]
                    segs.append(seg(k, t, t + hand, "dwell", 0, 0, "empty_trailer", lab, note="load")); ev(k, t, "load", 0, lab); t += hand
                    segs.append(seg(k, t, t + m[2], "travel", 0, cn, carry, lab, d[2])); t += m[2]
                    arrive = finish = t
                else:
                    d = [D[0][cn], D[cn][0]]
                    m = _split(mins(sum(d)), [d[0], d[1]])
                    m[0] = mins(d[0])
                    m[1] = mins(sum(d)) - m[0]
                    segs.append(seg(k, 0, m[0], "travel", 0, cn, "none", lab, d[0]))
                    arrive = m[0]
                    ev(k, arrive, "pickup", cn, lab)
                    segs.append(seg(k, arrive, arrive + m[1], "travel", cn, 0, carry, lab, d[1]))
                    finish = arrive + m[1]
            else:
                ctask, cfin, cc = cur
                t = cfin
                if ctask.type in Q_TYPES:
                    if task.type in Q_TYPES:
                        d = [D[0][tc], D[tc][cn], D[cn][0]]
                        t_arr = mins(d[0] + d[1])
                        m12 = _split(t_arr, [d[0], d[1]])
                        t_all = mins(sum(d))
                        segs.append(seg(k, t, t + m12[0], "travel", 0, tc, "empty_trailer", lab, d[0])); t += m12[0]
                        inv_events.append((t, +1, tc)); ev(k, t, "unhook", tc, lab)
                        segs.append(seg(k, t, t + hand, "dwell", tc, tc, "none", lab, note="swap")); t += hand
                        segs.append(seg(k, t, t + m12[1], "travel", tc, cn, "none", lab, d[1])); t += m12[1]
                        arrive = t
                        ev(k, arrive, "pickup", cn, lab)
                        m3 = t_all - t_arr
                        segs.append(seg(k, t, t + m3, "travel", cn, 0, carry, lab, d[2])); t += m3
                        finish = t
                    else:
                        d = D[0][cn]
                        segs.append(seg(k, t, t + hand * 2, "dwell", 0, 0, "empty_trailer", lab, note="unload+load")); ev(k, t, "load", 0, lab); t += hand * 2
                        T = mins(d)
                        segs.append(seg(k, t, t + T, "travel", 0, cn, carry, lab, d)); t += T
                        arrive = finish = t
                else:
                    if task.type in Q_TYPES:
                        d = [D[cc][cn], D[cn][0]]
                        t1 = mins(d[0])
                        t_all = mins(sum(d))
                        segs.append(seg(k, t, t + t1, "travel", cc, cn, "none", lab, d[0])); t += t1
                        arrive = t
                        ev(k, arrive, "pickup", cn, lab)
                        segs.append(seg(k, t, t + (t_all - t1), "travel", cn, 0, carry, lab, d[1])); t += t_all - t1
                        finish = t
                    else:
                        d = [D[cc][tc], D[tc][0], D[0][cn]]
                        T = mins(sum(d))
                        m = _split(T, d)
                        segs.append(seg(k, t, t + m[0], "travel", cc, tc, "none", lab, d[0])); t += m[0]
                        inv_events.append((t, -1, tc)); ev(k, t, "hook", tc, lab)
                        segs.append(seg(k, t, t + m[1], "travel", tc, 0, "empty_trailer", lab, d[1])); t += m[1]
                        segs.append(seg(k, t, t + hand, "dwell", 0, 0, "empty_trailer", lab, note="load")); ev(k, t, "load", 0, lab); t += hand
                        segs.append(seg(k, t, t + m[2], "travel", 0, cn, carry, lab, d[2])); t += m[2]
                        arrive = finish = t
            if task.type in S_TYPES:
                ev(k, arrive, "drop", cn, lab)
            if not task.urgent:
                if arrive < task.early_min:
                    ev(k, arrive, "early", cn, lab, minutes=task.early_min - arrive)
                elif arrive > task.late_min:
                    ev(k, arrive, "late", cn, lab, minutes=arrive - task.late_min)
            cur = (task, finish, cn)
            t_end = finish
            segs[-1]["task_done"] = True

        # 收车
        if cur is not None:
            ctask, cfin, cc = cur
            t = cfin
            if ctask.type in S_TYPES:
                bd = D[cc][0]
                T = mins(bd)
                segs.append(seg(k, t, t + T, "travel", cc, 0, "none", None, bd, note="return")); t += T
            else:
                tcn = nearest_tc_return(inst, 0)
                d = [D[0][tcn], D[tcn][0]]
                T = mins(sum(d))
                m = _split(T, d)
                segs.append(seg(k, t, t + m[0], "travel", 0, tcn, "empty_trailer", None, d[0], note="return trailer")); t += m[0]
                inv_events.append((t, +1, tcn)); ev(k, t, "unhook", tcn, None)
                segs.append(seg(k, t, t + hand, "dwell", tcn, tcn, "none", None, note="return trailer")); t += hand
                segs.append(seg(k, t, t + m[1], "travel", tcn, 0, "none", None, d[1], note="return")); t += m[1]
            ev(k, t, "return_dc", 0, None)
            t_end = t
        tractors.append({"k": k + 1, "segments": segs, "end_time": t_end if entries else 0,
                         "km": round(sum(s["km"] for s in segs), 2)})

    # TC 库存时间线（现实口径：同一时刻先还后取）
    inv = {tc: inst.tcs[tc - inst.tc_first]["trailers"] for tc in inst.tc_nodes()}
    series = {tc - inst.tc_first + 1: [(0, inv[tc])] for tc in inst.tc_nodes()}
    for t, d, tc in sorted(inv_events, key=lambda e: (e[0], -e[1])):
        inv[tc] += d
        series[tc - inst.tc_first + 1].append((t, inv[tc]))
    events.sort(key=lambda e: (e["t"], e["tractor"]))

    geometry = {}
    if use_roads:
        from .geometry import load_geometry
        g = load_geometry(company)["pairs"]
        for a, b in sorted(used_pairs):
            geometry[f"{a}-{b}"] = g[f"{a}-{b}"]
    return {"instance": inst.id, "coord_system": inst.coord_system, "horizon_min": inst.horizon_min,
            "nodes": {"dc": 0, "clients": {c["id"]: inst.client_node[c["id"]] for c in inst.clients},
                      "tcs": {t["id"]: inst.tc_node[t["id"]] for t in inst.tcs},
                      "xy": [list(p) for p in pts]},
            "tractors": tractors, "events": events, "tc_inventory": series,
            "geometry": geometry, "geometry_precision": 6 if use_roads else None,
            "km_total": round(sum(t["km"] for t in tractors), 2)}
