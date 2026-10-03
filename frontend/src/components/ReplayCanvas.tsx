import { useEffect, useMemo, useRef, useState } from "react";
import { pathFor, travelledPath, type Pos, type Trajectory } from "../lib/replay";

export const PALETTE = ["#165dff", "#f77234", "#00b42a", "#722ed1", "#f5319d", "#14c9c9", "#d91ad9", "#ff7d00", "#3491fa", "#7bc616", "#f53f3f", "#86909c", "#0fc6c2", "#9fdb1d", "#b71de8", "#ffb400"];
export const colorOf = (k: number) => PALETTE[(k - 1) % PALETTE.length];

interface Props {
  tr: Trajectory; t: number; pos: Pos[]; inventory: Record<string, number>; selected: number | null;
  showRoutes: boolean; showTrail: boolean; nodeState: Record<number, "done" | "late" | "early">; pending: Set<number>;
  attribution?: string; height?: number; zoomToTractors?: boolean;
}

export function ReplayCanvas({ tr, t, pos, inventory, selected, showRoutes, showTrail, nodeState, pending, attribution, height = 520, zoomToTractors = false }: Props) {
  const ref = useRef<HTMLCanvasElement>(null);
  const [boxW, setBoxW] = useState(0);        // 容器宽度变化（旋转手机、拉伸窗口）时重绘
  useEffect(() => {
    const c = ref.current; if (!c || typeof ResizeObserver === "undefined") return;
    const ro = new ResizeObserver(() => setBoxW(c.clientWidth)); ro.observe(c); return () => ro.disconnect();
  }, []);
  const geo = tr.coord_system === "wgs84";
  const lat0 = tr.nodes.xy[0][1];
  const kx = geo ? Math.cos((lat0 * Math.PI) / 180) : 1;

  // 投影：地图数据集（经纬度）等距圆柱，网格数据集线性
  const bounds = useMemo(() => {
    let pts: [number, number][] = tr.nodes.xy as [number, number][];
    if (zoomToTractors) {   // 只看一辆车：缩放到它实际走过的路线
      const acc: [number, number][] = [];
      for (const tt of tr.tractors) for (const sg of tt.segments) {
        if (sg.kind !== "travel" || sg.from === sg.to) { acc.push(tr.nodes.xy[sg.from] as [number, number]); continue; }
        for (const q of pathFor(tr, sg.from, sg.to).pts) acc.push(q);
      }
      if (acc.length > 1) pts = acc;
    }
    const xs = pts.map((p) => p[0] * kx), ys = pts.map((p) => p[1]);
    const pad = 0.07;
    const x0 = Math.min(...xs), x1 = Math.max(...xs), y0 = Math.min(...ys), y1 = Math.max(...ys);
    const dx = (x1 - x0) * pad || 1, dy = (y1 - y0) * pad || 1;
    return { x0: x0 - dx, x1: x1 + dx, y0: y0 - dy, y1: y1 + dy };
  }, [tr, kx, zoomToTractors]);

  useEffect(() => {
    const c = ref.current;
    if (!c) return;
    const dpr = window.devicePixelRatio || 1;
    const W = c.clientWidth, H = height;
    if (c.width !== W * dpr || c.height !== H * dpr) { c.width = W * dpr; c.height = H * dpr; }
    const g = c.getContext("2d")!;
    g.setTransform(dpr, 0, 0, dpr, 0, 0);
    const sx = (W - 20) / (bounds.x1 - bounds.x0), sy = (H - 20) / (bounds.y1 - bounds.y0);
    const s = Math.min(sx, sy);
    const ox = (W - (bounds.x1 - bounds.x0) * s) / 2, oy = (H - (bounds.y1 - bounds.y0) * s) / 2;
    const P = (x: number, y: number): [number, number] => [ox + (x * kx - bounds.x0) * s, H - (oy + (y - bounds.y0) * s)];

    g.fillStyle = "#f7f8fa"; g.fillRect(0, 0, W, H);
    if (!geo) {   // 网格数据集：淡网格
      g.strokeStyle = "#e5e6eb"; g.lineWidth = 1;
      for (let i = 0; i <= 10; i++) {
        const a = P(i * 10, 0), b = P(i * 10, 100); g.beginPath(); g.moveTo(a[0], a[1]); g.lineTo(b[0], b[1]); g.stroke();
        const c1 = P(0, i * 10), d = P(100, i * 10); g.beginPath(); g.moveTo(c1[0], c1[1]); g.lineTo(d[0], d[1]); g.stroke();
      }
    }
    // 真实道路（本计划用到的每一段）
    if (showRoutes) {
      g.strokeStyle = "rgba(134,144,156,0.45)"; g.lineWidth = 1.2;
      const seen = new Set<string>();
      for (const tt of tr.tractors) for (const sg of tt.segments) {
        if (sg.kind !== "travel" || sg.from === sg.to) continue;
        const key = `${sg.from}-${sg.to}`; if (seen.has(key)) continue; seen.add(key);
        const pts = pathFor(tr, sg.from, sg.to).pts;
        g.beginPath(); pts.forEach((q, i) => { const [x, y] = P(q[0], q[1]); i ? g.lineTo(x, y) : g.moveTo(x, y); }); g.stroke();
      }
    }
    // 拖尾：过去 15 个仿真分钟，沿真实道路走过的路径；分 5 段，越旧越淡
    if (showTrail) {
      const SLICES = 5, SPAN = 3;       // 每段 3 个仿真分钟
      for (const p of pos) {
        if (p.state === "idle") continue;
        g.strokeStyle = colorOf(p.k); g.lineWidth = selected === p.k ? 3 : 2; g.lineCap = "round"; g.lineJoin = "round";
        for (let i = 0; i < SLICES; i++) {
          const pts = travelledPath(tr, p.k, Math.max(0, t - (i + 1) * SPAN), Math.max(0, t - i * SPAN));
          if (pts.length < 2) continue;
          g.globalAlpha = 0.75 * (1 - i / SLICES);
          g.beginPath();
          pts.forEach((q, j) => { const [x, y] = P(q[0], q[1]); j ? g.lineTo(x, y) : g.moveTo(x, y); });
          g.stroke();
        }
        g.globalAlpha = 1;
      }
    }
    // 节点
    tr.nodes.xy.forEach((q, n) => {
      const [x, y] = P(q[0], q[1]);
      const isTc = Object.values(tr.nodes.tcs).includes(n);
      if (n === tr.nodes.dc) { g.fillStyle = "#1d2129"; g.fillRect(x - 7, y - 7, 14, 14); return; }
      if (isTc) {
        g.fillStyle = "#722ed1"; g.beginPath(); g.moveTo(x, y - 8); g.lineTo(x + 8, y); g.lineTo(x, y + 8); g.lineTo(x - 8, y); g.closePath(); g.fill();
        const id = Object.entries(tr.nodes.tcs).find(([, v]) => v === n)?.[0];
        const inv = id ? inventory[id] : undefined;
        if (inv !== undefined) {
          g.fillStyle = inv <= 0 ? "#f53f3f" : inv <= 1 ? "#ff7d00" : "#1d2129"; g.font = "bold 12px sans-serif"; g.fillText(String(inv), x + 10, y + 4);
        }
        return;
      }
      const st = nodeState[n];
      if (st) {
        g.fillStyle = "#00b42a"; g.beginPath(); g.arc(x, y, 3.8, 0, 7); g.fill();
        if (st !== "done") { g.strokeStyle = st === "late" ? "#f53f3f" : "#ff7d00"; g.lineWidth = 2; g.beginPath(); g.arc(x, y, 6.5, 0, 7); g.stroke(); }
      } else if (pending.has(n)) {
        g.strokeStyle = "#86909c"; g.lineWidth = 1.5; g.beginPath(); g.arc(x, y, 3.8, 0, 7); g.stroke();
      } else { g.fillStyle = "#c9cdd4"; g.beginPath(); g.arc(x, y, 2, 0, 7); g.fill(); }
    });
    // 车辆：牵引头 + 挂车状态
    for (const p of pos) {
      const [x, y] = P(p.x, p.y);
      const h = geo ? Math.atan2(-Math.sin(p.heading), Math.cos(p.heading) * kx) : -p.heading;
      g.save(); g.translate(x, y); g.rotate(p.state === "moving" ? h : 0);
      const col = colorOf(p.k);
      if (selected === p.k) { g.strokeStyle = "#1d2129"; g.lineWidth = 2; g.beginPath(); g.arc(0, 0, 12, 0, 7); g.stroke(); }
      if (p.trailer !== "none") {
        g.lineWidth = 1.6; g.strokeStyle = col;
        g.fillStyle = p.trailer === "loaded" ? col : p.trailer === "empty_container" ? col + "55" : "#ffffff";
        g.fillRect(-14, -3.5, 12, 7); g.strokeRect(-14, -3.5, 12, 7);
      }
      g.fillStyle = col; g.fillRect(-2, -3.5, 7, 7);
      if (p.state === "dwelling") { g.strokeStyle = "#1d2129"; g.lineWidth = 1; g.beginPath(); g.arc(0, 0, 9, 0, 7); g.stroke(); }
      g.restore();
    }
    if (attribution) { g.fillStyle = "rgba(29,33,41,0.55)"; g.font = "11px sans-serif"; g.fillText(attribution, 8, H - 8); }
  }, [tr, t, pos, inventory, selected, showRoutes, showTrail, nodeState, pending, bounds, geo, kx, height, attribution, zoomToTractors, boxW]);

  return <canvas ref={ref} style={{ width: "100%", height, borderRadius: 6, border: "1px solid var(--color-border-2)", display: "block" }} />;
}
