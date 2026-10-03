import { decodePolyline } from "./polyline";

export interface Segment {
  t0: number; t1: number; kind: "travel" | "dwell"; from: number; to: number; trailer: string; task: string | null; km: number;
  x0: number; y0: number; x1: number; y1: number; note?: string; task_done?: boolean;
}
export interface TrajEvent { t: number; tractor: number; kind: string; node: number; task: string | null; minutes?: number }
export interface Trajectory {
  coord_system: "grid" | "wgs84"; horizon_min: number;
  nodes: { dc: number; clients: Record<string, number>; tcs: Record<string, number>; xy: [number, number][] };
  tractors: { k: number; segments: Segment[]; end_time: number; km: number }[];
  events: TrajEvent[]; tc_inventory: Record<string, [number, number][]>; geometry: Record<string, string>; geometry_precision: number | null;
  km_total: number;
}

export interface Pos { x: number; y: number; trailer: string; state: "moving" | "dwelling" | "idle"; heading: number; k: number }

type Path = { pts: [number, number][]; cum: number[]; total: number };
const pathCache = new WeakMap<Trajectory, Map<string, Path>>();

function lengthOf(pts: [number, number][]): { cum: number[]; total: number } {
  const cum = [0];
  for (let i = 1; i < pts.length; i++) {
    const dx = pts[i][0] - pts[i - 1][0], dy = pts[i][1] - pts[i - 1][1];
    cum.push(cum[i - 1] + Math.hypot(dx, dy));
  }
  return { cum, total: cum[cum.length - 1] };
}

/** 一个转场（from→to）的折线：地图数据集沿真实道路，网格数据集是直线。 */
export function pathFor(tr: Trajectory, from: number, to: number): Path {
  let cache = pathCache.get(tr);
  if (!cache) { cache = new Map(); pathCache.set(tr, cache); }
  const key = `${from}-${to}`;
  let p = cache.get(key);
  if (p) return p;
  const enc = tr.geometry[key];
  const pts = enc ? decodePolyline(enc, tr.geometry_precision ?? 6) : [tr.nodes.xy[from], tr.nodes.xy[to]];
  const { cum, total } = lengthOf(pts);
  p = { pts, cum, total };
  cache.set(key, p);
  return p;
}

/** 沿折线按比例 f(0..1)（按折线长度）取点，并返回行进方向。 */
export function along(p: Path, f: number): { x: number; y: number; heading: number } {
  const target = Math.min(1, Math.max(0, f)) * p.total;
  if (p.total === 0) return { x: p.pts[0][0], y: p.pts[0][1], heading: 0 };
  let i = 1;
  while (i < p.cum.length - 1 && p.cum[i] < target) i++;
  const a = p.pts[i - 1], b = p.pts[i];
  const seg = p.cum[i] - p.cum[i - 1] || 1;
  const u = (target - p.cum[i - 1]) / seg;
  return { x: a[0] + (b[0] - a[0]) * u, y: a[1] + (b[1] - a[1]) * u, heading: Math.atan2(b[1] - a[1], b[0] - a[0]) };
}

/** 时刻 t 各车的位置与状态（按轨迹插值，前端不自行推算时间）。 */
export function positionsAt(tr: Trajectory, t: number): Pos[] {
  const dc = tr.nodes.xy[tr.nodes.dc];
  return tr.tractors.map((tt) => {
    const segs = tt.segments;
    if (!segs.length || t <= segs[0].t0) return { x: dc[0], y: dc[1], trailer: "none", state: "idle", heading: 0, k: tt.k };
    const last = segs[segs.length - 1];
    if (t >= last.t1) return { x: tr.nodes.xy[last.to][0], y: tr.nodes.xy[last.to][1], trailer: "none", state: "idle", heading: 0, k: tt.k };
    let lo = 0, hi = segs.length - 1;
    while (lo < hi) { const mid = (lo + hi + 1) >> 1; if (segs[mid].t0 <= t) lo = mid; else hi = mid - 1; }
    const s = segs[lo];
    if (s.kind === "dwell" || s.t1 === s.t0 || s.from === s.to) {
      return { x: tr.nodes.xy[s.from][0], y: tr.nodes.xy[s.from][1], trailer: s.trailer, state: s.kind === "dwell" ? "dwelling" : "moving", heading: 0, k: tt.k };
    }
    const f = (t - s.t0) / (s.t1 - s.t0);
    const a = along(pathFor(tr, s.from, s.to), f);
    return { x: a.x, y: a.y, trailer: s.trailer, state: "moving", heading: a.heading, k: tt.k };
  });
}

/** 时刻 t 的各挂车场库存（时间线是阶梯函数）。 */
export function inventoryAt(tr: Trajectory, t: number): Record<string, number> {
  const out: Record<string, number> = {};
  for (const [id, series] of Object.entries(tr.tc_inventory)) {
    let v = series[0][1];
    for (const [tt, val] of series) { if (tt <= t) v = val; else break; }
    out[id] = v;
  }
  return out;
}

export interface Counters { done: number; late: number; early: number; km: number; moving: number; dwelling: number }
export function countersAt(tr: Trajectory, t: number, pos: Pos[]): Counters {
  let done = 0, late = 0, early = 0;
  for (const e of tr.events) {
    if (e.t > t) break;
    if (e.kind === "drop" || e.kind === "pickup") done++;
    else if (e.kind === "late") late++;
    else if (e.kind === "early") early++;
  }
  let km = 0;
  for (const tt of tr.tractors) {
    for (const s of tt.segments) {
      if (s.kind !== "travel" || s.t0 >= t) continue;
      km += s.t1 <= t || s.t1 === s.t0 ? s.km : s.km * ((t - s.t0) / (s.t1 - s.t0));
    }
  }
  return { done, late, early, km, moving: pos.filter((p) => p.state === "moving").length, dwelling: pos.filter((p) => p.state === "dwelling").length };
}

/** 下一个事件的时刻（用于"下一个事件"按钮）。 */
export function nextEventTime(tr: Trajectory, t: number): number | null {
  for (const e of tr.events) if (e.t > t) return e.t;
  return null;
}

/** 折线上按长度比例 [f0, f1] 的一段（含两端插值点）。 */
function slicePath(p: Path, f0: number, f1: number): [number, number][] {
  if (p.total === 0) return [p.pts[0]];
  const a = Math.min(1, Math.max(0, f0)) * p.total, b = Math.min(1, Math.max(0, f1)) * p.total;
  const at = (d: number): [number, number] => {
    let i = 1;
    while (i < p.cum.length - 1 && p.cum[i] < d) i++;
    const seg = p.cum[i] - p.cum[i - 1] || 1, u = (d - p.cum[i - 1]) / seg;
    return [p.pts[i - 1][0] + (p.pts[i][0] - p.pts[i - 1][0]) * u, p.pts[i - 1][1] + (p.pts[i][1] - p.pts[i - 1][1]) * u];
  };
  const out: [number, number][] = [at(a)];
  for (let i = 0; i < p.cum.length; i++) if (p.cum[i] > a && p.cum[i] < b) out.push(p.pts[i]);
  out.push(at(b));
  return out;
}

/** 第 k 辆车在时间段 [ta, tb] 内**沿真实道路**走过的折线（拖尾用；停留时不产生新点）。 */
export function travelledPath(tr: Trajectory, k: number, ta: number, tb: number): [number, number][] {
  const tt = tr.tractors.find((x) => x.k === k);
  if (!tt || tb <= ta) return [];
  const out: [number, number][] = [];
  for (const s of tt.segments) {
    if (s.kind !== "travel" || s.from === s.to || s.t1 <= ta || s.t0 >= tb || s.t1 === s.t0) continue;
    const f0 = (Math.max(s.t0, ta) - s.t0) / (s.t1 - s.t0), f1 = (Math.min(s.t1, tb) - s.t0) / (s.t1 - s.t0);
    out.push(...slicePath(pathFor(tr, s.from, s.to), f0, f1));
  }
  return out;
}
