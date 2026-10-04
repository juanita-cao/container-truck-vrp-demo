import { Alert, Button, Card, Empty, Radio, Select, Skeleton, Slider, Space, Switch, Tag, Typography } from "@arco-design/web-react";
import { IconPause, IconPlayArrow, IconSkipNext, IconRefresh } from "@arco-design/web-react/icon";
import { useQuery } from "@tanstack/react-query";
import { useEffect, useMemo, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate, useSearchParams } from "react-router-dom";
import { useNarrow } from "../lib/useNarrow";
import { get, type RecordedRun, type RunRecord } from "../api/client";
import { Gantt } from "../components/Gantt";
import { ErrorNote } from "../components/ErrorNote";
import { colorOf, ReplayCanvas } from "../components/ReplayCanvas";
import { clock, num } from "../lib/format";
import { countersAt, inventoryAt, nextEventTime, positionsAt, type Trajectory } from "../lib/replay";
import { usePrefs } from "../state/prefs";

const SPEEDS = [1, 5, 15, 60];

export function ReplayPage() {
  const { t } = useTranslation();
  const p = usePrefs();
  const nav = useNavigate();
  const [sp] = useSearchParams();
  // 没有指定运行时：最近一次现场运行 → 否则用预先录好的（当前算例的"明日排程"优先）
  const rec = useQuery({ queryKey: ["recorded", p.dataset], queryFn: () => get<RecordedRun[]>("/recorded-runs", { dataset: p.dataset }) });
  const recorded = rec.data?.filter((r) => r.instance === p.instance) ?? [];
  const fallback = (recorded.find((r) => r.mode === "tomorrow") ?? recorded[0])?.run_id ?? null;
  const runId = sp.get("run") ?? p.recent.find((r) => r.instance === p.instance)?.run_id ?? fallback;
  const lang = p.lang;
  const narrowScreen = useNarrow(768);

  const run = useQuery({ queryKey: ["run", runId], enabled: !!runId, queryFn: () => get<RunRecord>(`/runs/${runId}`) });
  const trq = useQuery({ queryKey: ["traj", runId], enabled: !!runId && run.isSuccess, queryFn: () => get<Trajectory>(`/runs/${runId}/trajectory`) });

  const [tNow, setT] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [speed, setSpeed] = useState(15);
  const [showRoutes, setShowRoutes] = useState(true);
  const [showTrail, setShowTrail] = useState(false);   // 拖尾默认关闭，需要时再打开
  const [focus, setFocus] = useState<number | null>(null);   // 只显示某一辆车（null = 全部）
  const raf = useRef<number | null>(null);
  const last = useRef<number>(0);

  const full = trq.data;
  const maxT = useMemo(() => (full ? Math.max(...full.tractors.map((x) => x.end_time), 1) : 1), [full]);
  // 聚焦一辆车时：地图、计数、事件、节点状态都只用这辆车的数据（挂车场库存是全局的，保持不变）
  const tr = useMemo(() => (full && focus !== null
    ? { ...full, tractors: full.tractors.filter((x) => x.k === focus), events: full.events.filter((e) => e.tractor === focus) }
    : full), [full, focus]);

  useEffect(() => { setT(0); setPlaying(false); setFocus(null); }, [runId]);
  // 首页即回放：第一次进入且没有指定运行时自动开始播放（系统开启"减少动画"时不自动播放）
  const autoplayed = useRef(false);
  useEffect(() => {
    if (autoplayed.current || !full || sp.get("run")) return;
    autoplayed.current = true;
    if (!window.matchMedia("(prefers-reduced-motion: reduce)").matches) setPlaying(true);
  }, [full, sp]);
  useEffect(() => {
    if (!playing || !tr) return;
    const loop = (ts: number) => {
      if (!last.current) last.current = ts;
      const dt = (ts - last.current) / 1000; last.current = ts;
      setT((cur) => { const n = cur + dt * speed; if (n >= maxT) { setPlaying(false); return maxT; } return n; });
      raf.current = requestAnimationFrame(loop);
    };
    last.current = 0;
    raf.current = requestAnimationFrame(loop);
    return () => { if (raf.current) cancelAnimationFrame(raf.current); };
  }, [playing, speed, maxT, tr]);

  const pos = useMemo(() => (tr ? positionsAt(tr, tNow) : []), [tr, tNow]);
  const inv = useMemo(() => (tr ? inventoryAt(tr, tNow) : {}), [tr, tNow]);
  const cnt = useMemo(() => (tr ? countersAt(tr, tNow, pos) : null), [tr, tNow, pos]);
  const { nodeState, pending } = useMemo(() => {
    const st: Record<number, "done" | "late" | "early"> = {};
    const pend = new Set<number>();
    if (tr) for (const e of tr.events) {
      if (e.kind === "drop" || e.kind === "pickup") { if (e.t <= tNow) st[e.node] = st[e.node] ?? "done"; else pend.add(e.node); }
      if (e.t <= tNow && (e.kind === "late" || e.kind === "early")) st[e.node] = e.kind;
    }
    return { nodeState: st, pending: pend };
  }, [tr, tNow]);
  const log = useMemo(() => (tr ? tr.events.filter((e) => e.t <= tNow && e.kind !== "early" && e.kind !== "late").slice(-10).reverse() : []), [tr, tNow]);
  const nodeLabel = (n: number) => {
    if (!tr) return String(n);
    const tc = Object.entries(tr.nodes.tcs).find(([, v]) => v === n)?.[0];
    return tc ? `T${tc}` : n === tr.nodes.dc ? t("replay.node.dc") : `C${n}`;
  };

  if (!runId) return <Empty description={<Space direction="vertical"><span>{t("replay.noRun")}</span><Button type="primary" onClick={() => nav("/plan")}>{t("replay.goPlan")}</Button></Space>} />;
  const geo = tr?.coord_system === "wgs84";

  return (
    <Space direction="vertical" size="medium" style={{ width: "100%" }}>
      <div>
        <Typography.Title heading={4} className="page-title">{t("replay.title")}</Typography.Title>
        <Typography.Text type="secondary">{t("replay.subtitle")}</Typography.Text>
      </div>
      {(run.isLoading || trq.isLoading) && <Skeleton text={{ rows: 8 }} animation />}
      {run.isError && <ErrorNote error={run.error} onRetry={() => run.refetch()} />}
      {trq.isError && <ErrorNote error={trq.error} onRetry={() => trq.refetch()} />}
      {tr && run.data && cnt && (
        <>
          <Card size="small">
            <Space size="large" wrap style={{ width: "100%" }}>
              <span>{t("replay.source")}: <Tag>{run.data.instance}</Tag><Tag color="arcoblue">{run.data.method}</Tag>{run.data.recorded && <Tag color="green">{t("replay.recorded")}</Tag>}</span>
              <span style={{ fontSize: 26, fontWeight: 700, fontVariantNumeric: "tabular-nums" }}>{clock(tNow)}</span>
              <Space>
                <Button type="primary" shape="circle" icon={playing ? <IconPause /> : <IconPlayArrow />} aria-label={playing ? t("replay.pause") : t("replay.play")}
                  onClick={() => { if (tNow >= maxT) setT(0); setPlaying(!playing); }} />
                <Button shape="circle" icon={<IconRefresh />} aria-label={t("replay.restart")} onClick={() => { setT(0); setPlaying(false); }} />
                <Button shape="circle" icon={<IconSkipNext />} aria-label={t("replay.nextEvent")} onClick={() => { const n = nextEventTime(tr, tNow); if (n !== null) setT(n); }} />
              </Space>
              <Space>{t("replay.speed")}
                <Radio.Group type="button" size="small" value={speed} onChange={setSpeed} options={SPEEDS.map((s) => ({ value: s, label: `${s}×` }))} />
                <Typography.Text type="secondary" style={{ fontSize: 12 }}>{t("replay.speedUnit")}</Typography.Text>
              </Space>
              <Space>{t("replay.vehicle")}
                <Select size="small" style={{ width: 150 }} value={focus ?? 0} onChange={(v) => setFocus(v === 0 ? null : v)}
                  options={[{ value: 0, label: t("replay.allTrucks") }, ...(full?.tractors ?? []).filter((x) => x.segments.length).map((x) => ({ value: x.k, label: `K${x.k}` }))]} />
              </Space>
              <Space><Switch size="small" checked={showRoutes} onChange={setShowRoutes} /> {t("replay.showRoutes")}<Switch size="small" checked={showTrail} onChange={setShowTrail} /> {t("replay.showTrail")}</Space>
            </Space>
            <Slider style={{ marginTop: 8 }} min={0} max={Math.ceil(maxT)} step={1} value={tNow} onChange={(v) => { setT(Number(v)); }} formatTooltip={(v) => clock(Number(v))} />
          </Card>

          <div className="replay-wrap">
            <Card bodyStyle={{ padding: 8 }}>
              <ReplayCanvas tr={tr} t={tNow} pos={pos} inventory={inv} selected={focus} showRoutes={showRoutes} showTrail={showTrail}
                nodeState={nodeState} pending={pending} attribution={geo ? t("common.dataBy") : undefined} zoomToTractors={focus !== null} height={narrowScreen ? 340 : 520} />
              <Space wrap size="medium" style={{ marginTop: 8, fontSize: 12 }}>
                {(["none", "empty_trailer", "loaded", "empty_container"] as const).map((k) => <span key={k}><span className="legend-dot" style={{ background: { none: "#c9cdd4", empty_trailer: "#bedaff", loaded: "#165dff", empty_container: "#14c9c9" }[k] }} />{t(`replay.trailer.${k}`)}</span>)}
                <span>■ {t("replay.node.dc")}</span><span style={{ color: "#722ed1" }}>◆ {t("replay.node.tc")}</span><span>● {t("replay.node.client")}</span>
              </Space>
            </Card>
            <Space direction="vertical" style={{ width: "100%" }} size="small">
              <Card size="small" title={t("replay.counters")}>
                <div style={{ lineHeight: 2 }}>
                  <div>{t("replay.done")}: <b>{cnt.done}</b></div>
                  <div>{t("replay.late")}: <b className="bad">{cnt.late}</b> · {t("replay.early")}: <b style={{ color: "rgb(var(--orange-6))" }}>{cnt.early}</b></div>
                  <div>{t("replay.km")}: <b>{num(cnt.km, lang)}</b> / {num(focus !== null ? (tr.tractors[0]?.km ?? 0) : tr.km_total, lang)}</div>
                  <div>{t("replay.onRoad")}: <b>{cnt.moving}</b> · {t("replay.dwelling")}: <b>{cnt.dwelling}</b></div>
                </div>
              </Card>
              <Card size="small" title={t("replay.inventory")}>
                <Space wrap>{Object.entries(inv).map(([id, v]) => <Tag key={id} color={v <= 0 ? "red" : v <= 1 ? "orange" : "purple"}>◆ T{id}: {v}</Tag>)}</Space>
              </Card>
              <Card size="small" title={t("replay.eventLog")}>
                <div className="event-log">
                  {log.length === 0 && <Typography.Text type="secondary">{t("common.noData")}</Typography.Text>}
                  {log.map((e, i) => (
                    <div key={i}><span style={{ color: "var(--color-text-3)" }}>{clock(e.t)}</span> <span style={{ color: colorOf(e.tractor) }}>●</span> {t(`replay.events.${e.kind}`, { tractor: `K${e.tractor}`, node: nodeLabel(e.node), task: e.task ?? "", minutes: e.minutes ?? 0 })}</div>
                  ))}
                </div>
              </Card>
            </Space>
          </div>
          <Card size="small" title={t("replay.gantt")}><Gantt tr={full ?? tr} t={tNow} selected={focus} onSelect={(k) => setFocus(focus === k ? null : k)} horizon={Math.max(maxT, 60)} /></Card>
          {focus !== null && <Alert type="info" content={`K${focus} · ${t("replay.onlyHint")}`} />}
          {geo && <Alert type="info" content={t("common.dataBy")} />}
        </>
      )}
    </Space>
  );
}
