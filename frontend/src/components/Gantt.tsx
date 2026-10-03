import type { Trajectory } from "../lib/replay";
import { colorOf } from "./ReplayCanvas";

const FILL: Record<string, string> = { none: "#c9cdd4", empty_trailer: "#bedaff", loaded: "#165dff", empty_container: "#14c9c9" };

export function Gantt({ tr, t, selected, onSelect, horizon }: { tr: Trajectory; t: number; selected: number | null; onSelect: (k: number) => void; horizon: number }) {
  const rowH = 14, left = 34, W = 1000, H = tr.tractors.length * rowH + 16;
  const X = (m: number) => left + (m / horizon) * (W - left - 6);
  return (
    <div className="scroll-x"><svg viewBox={`0 0 ${W} ${H}`} style={{ width: "100%", minWidth: 720, display: "block" }} role="img">
      {[0, 120, 240, 360, 480, 600, 720].filter((m) => m <= horizon).map((m) => (
        <g key={m}><line x1={X(m)} x2={X(m)} y1={0} y2={H - 14} stroke="#e5e6eb" /><text x={X(m)} y={H - 3} fontSize="10" textAnchor="middle" fill="#86909c">{String(8 + m / 60).padStart(2, "0")}:00</text></g>
      ))}
      {tr.tractors.map((tt, i) => (
        <g key={tt.k} onClick={() => onSelect(tt.k)} style={{ cursor: "pointer" }}>
          <text x={2} y={i * rowH + 11} fontSize="10" fill={colorOf(tt.k)} fontWeight={selected === tt.k ? 700 : 400}>K{tt.k}</text>
          {tt.segments.map((s, j) => s.t1 > s.t0 && (
            <rect key={j} x={X(s.t0)} y={i * rowH + 2} width={Math.max(1, X(s.t1) - X(s.t0))} height={rowH - 4} fill={FILL[s.trailer] ?? "#c9cdd4"}
              opacity={s.kind === "dwell" ? 1 : 0.85} stroke={s.kind === "dwell" ? "#1d2129" : "none"} strokeWidth={s.kind === "dwell" ? 0.6 : 0} />
          ))}
        </g>
      ))}
      <line x1={X(t)} x2={X(t)} y1={0} y2={H - 14} stroke="#f53f3f" strokeWidth={1.5} />
    </svg></div>
  );
}
