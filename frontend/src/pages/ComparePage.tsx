import { Alert, Button, Card, Collapse, Grid, InputNumber, Skeleton, Space, Statistic, Table, Tag, Typography } from "@arco-design/web-react";
import { useQuery } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";
import { ApiError, get, http, type CompareColumn, type CompareResp, type InstanceSummary, type ScalingRow } from "../api/client";
import { EChart } from "../components/EChart";
import { ErrorNote } from "../components/ErrorNote";
import { delta, money, num, pct } from "../lib/format";
import { useNarrow } from "../lib/useNarrow";
import { usePrefs } from "../state/prefs";

const { Row, Col } = Grid;
// 故事线：不甩挂 → 甩挂（人工规则）→ 立即排程（甩挂+优化）→ 明日排程（甩挂+更强优化）
const COLS = [
  { key: "C0", title: "colTraditional", sub: "colTraditionalSub", color: "#f53f3f", how: "traditional" },
  { key: "H0", title: "colManual", sub: "colManualSub", color: "#86909c", how: "manual" },
  { key: "M2", title: "colNow", sub: "colNowSub", color: "#165dff", how: "now" },
  { key: "M3", title: "colTomorrow", sub: "colTomorrowSub", color: "#00b42a", how: "tomorrow" },
] as const;

export function ComparePage() {
  const narrow = useNarrow(768);
  const axisLabel = narrow ? { interval: 0, width: 72, overflow: "break" as const, fontSize: 10 } : { interval: 0 };   // 手机上图表分类名折行，避免互相重叠
  const { t } = useTranslation();
  const p = usePrefs();
  const nav = useNavigate();
  const [days, setDays] = useState(300);
  const lang = p.lang;
  const q = useQuery({
    queryKey: ["compare", p.dataset, p.instance], enabled: !!p.instance,
    queryFn: () => get<CompareResp>("/compare", { instance: p.instance, dataset: p.dataset, include_advanced: true }),
  });
  const [cstate, setCstate] = useState<"idle" | "running" | "error">("idle");
  async function runNow() {
    setCstate("running");
    try {
      const r = await http.post<{ compare_job: string }>("/compare/run", { dataset: p.dataset, instance: p.instance, budget_s: 10, seeds: 1 });
      const timer = window.setInterval(async () => {
        const st = await get<{ status: string }>(`/compare/jobs/${r.data.compare_job}`);
        if (st.status === "DONE") { window.clearInterval(timer); setCstate("idle"); q.refetch(); }
        if (st.status === "ERROR") { window.clearInterval(timer); setCstate("error"); }
      }, 1000);
    } catch { setCstate("error"); }
  }
  const insts = useQuery({ queryKey: ["instances", p.dataset], queryFn: () => get<InstanceSummary[]>("/instances", { dataset: p.dataset }) });
  const scaling = useQuery({ queryKey: ["scaling"], queryFn: () => get<{ rows: ScalingRow[]; limit_s: number }>("/scaling") });
  const cols = q.data?.columns ?? [];
  const find = (k: string) => cols.find((c) => c.method === k) as CompareColumn | undefined;
  const c0 = find("C0");
  const h0 = find("H0");
  const cur = q.data?.currency ?? "SGD";
  const symbol = money(0, cur, lang).replace(/[\d\s.,]/g, "");
  const meta = (insts.data ?? []).find((i) => i.name === p.instance);
  const base = c0 ?? h0;

  const story = useMemo(() => ({
    tooltip: { trigger: "axis" as const }, grid: { left: 70, right: 20, top: 24, bottom: 36 },
    xAxis: { type: "category" as const, data: COLS.map((c) => t(`compare.${c.title}`)), axisLabel },
    yAxis: { type: "value" as const },
    series: [{ type: "bar" as const, barMaxWidth: 70, data: COLS.map((c) => ({ value: Math.round(find(c.key)?.cost ?? 0), itemStyle: { color: c.color } })),
      label: { show: true, position: "top" as const, formatter: (x: { value?: unknown }) => money(Number(x.value ?? 0), cur, lang) } }],
  }), [q.data, t, lang]);   // eslint-disable-line react-hooks/exhaustive-deps

  const fleet = useMemo(() => {
    const m = q.data?.min_tractors;
    return {
      tooltip: { trigger: "axis" as const }, grid: { left: 40, right: 20, top: 16, bottom: 36 },
      xAxis: { type: "category" as const, data: [t("compare.fleetTraditional"), t("compare.fleetDropPull"), t("compare.fleetStandard")], axisLabel },
      yAxis: { type: "value" as const },
      series: [{ type: "bar" as const, barMaxWidth: 60, label: { show: true, position: "top" as const },
        data: [{ value: m?.C0 ?? 0, itemStyle: { color: "#f53f3f" } }, { value: m?.H0 ?? 0, itemStyle: { color: "#86909c" } }, { value: m?.["M0-R"] ?? 0, itemStyle: { color: "#165dff" } }] }],
    };
  }, [q.data, t]);

  const serveAll = useMemo(() => {
    const sa = q.data?.serve_all ?? [];
    return {
      tooltip: { trigger: "axis" as const }, grid: { left: 70, right: 20, top: 28, bottom: 52 },
      xAxis: { type: "category" as const, axisLabel,
        data: sa.map((x) => `${t(`compare.${COLS.find((c) => c.key === x.method)!.title}`)}\n${x.tractors} ${t("compare.trucks")}`) },
      yAxis: { type: "value" as const },
      series: [{ type: "bar" as const, barMaxWidth: 70, data: sa.map((x) => ({ value: Math.round(x.cost), itemStyle: { color: COLS.find((c) => c.key === x.method)!.color } })),
        label: { show: true, position: "top" as const, formatter: (x: { value?: unknown }) => money(Number(x.value ?? 0), cur, lang) } }],
    };
  }, [q.data, t, lang]);   // eslint-disable-line react-hooks/exhaustive-deps

  const curve = useMemo(() => {
    const pts = q.data?.columns.find((c) => c.method === "M3")?.trace ?? [];
    return {
      tooltip: { trigger: "axis" as const }, grid: { left: 64, right: 20, top: 24, bottom: 36 },
      xAxis: { type: "value" as const, name: t("compare.curveX") },
      yAxis: { type: "value" as const, name: t("compare.curveY"), scale: true },
      series: [{ type: "line" as const, step: "end" as const, data: pts, showSymbol: false, itemStyle: { color: "#00b42a" } }],
    };
  }, [q.data, t]);

  const scalingRows = useMemo(() => {
    const by: Record<number, ScalingRow[]> = {};
    (scaling.data?.rows ?? []).forEach((x) => (by[x.n] ||= []).push(x));
    return Object.entries(by).map(([n, xs]) => ({
      n: Number(n), proven: xs.filter((x) => x.m4_proven_optimal).length, total: xs.length, time: Math.max(...xs.map((x) => x.m4_runtime_s)),
    }));
  }, [scaling.data]);

  if (!p.instance) return <Alert type="info" content={t("plan.noInstance")} />;

  return (
    <Space direction="vertical" size="medium" style={{ width: "100%" }}>
      <div>
        <Typography.Title heading={4} className="page-title">{t("compare.title")}</Typography.Title>
        <Typography.Text type="secondary">{t("compare.subtitle")}</Typography.Text>
      </div>
      {q.isLoading && <Skeleton text={{ rows: 8 }} animation />}
      {q.isError && (q.error instanceof ApiError && q.error.code === "COMPARISON_NOT_PRECOMPUTED" ? (
        <Alert type="info" content={<Space direction="vertical"><span>{t("compare.scenarioHint")}</span>
          <Button type="primary" loading={cstate === "running"} onClick={runNow}>{cstate === "running" ? t("compare.running") : t("compare.runNow")}</Button>
          {cstate === "error" && <ErrorNote error={new ApiError("SOLVER_ERROR")} />}</Space>} />
      ) : <ErrorNote error={q.error} onRetry={() => q.refetch()} />)}
      {q.data && base && (
        <>
          <Alert type="info" content={<Space direction="vertical" size={2}>
            <b>{t("compare.sameFleet", { n: q.data.tractors })}{meta ? ` · ${meta.tasks} ${t("week.tasks").toLowerCase()}` : ""}</b>
            <span>{t("compare.assumptionService", { lo: 60, hi: 360 })}</span>
          </Space>} />
          {q.data.serve_all && (
            <Card title={<b>{t("compare.serveAllTitle")}</b>} style={{ borderLeft: "4px solid #00b42a" }}>
              <Row gutter={12} align="center">
                <Col xs={24} lg={14}><EChart option={serveAll} height={270} /></Col>
                <Col xs={24} lg={10}>
                  <Space direction="vertical" style={{ width: "100%" }} size="small">
                    {q.data.serve_all.map((x) => {
                      const c = COLS.find((cc) => cc.key === x.method)!;
                      return (
                        <div key={x.method} style={{ display: "flex", justifyContent: "space-between" }}>
                          <span><span className="legend-dot" style={{ background: c.color }} />{t(`compare.${c.title}`)} · {x.tractors} {t("compare.trucks")}</span>
                          <span><b>{money(x.cost, cur, lang)}</b>{x.method !== "C0" && <span className="good"> {delta(x.vs_traditional_pct, lang)}</span>}</span>
                        </div>
                      );
                    })}
                    <Typography.Text type="secondary" style={{ fontSize: 12 }}>{t("compare.serveAllNote")}</Typography.Text>
                  </Space>
                </Col>
              </Row>
            </Card>
          )}
          <div><Typography.Title heading={6} style={{ margin: "4px 0" }}>{t("compare.sameTrucksTitle")}</Typography.Title><Typography.Text type="secondary" style={{ fontSize: 12 }}>{t("compare.sameTrucksNote")}</Typography.Text></div>
          <Row gutter={12}>
            {COLS.map((c) => {
              const col = find(c.key);
              if (!col) return null;
              const saved = base.cost - col.cost;
              return (
                <Col key={c.key} xs={24} md={12} xl={6} style={{ marginBottom: 12 }}>
                  <Card className="method-card" style={{ borderTop: `3px solid ${c.color}` }}
                    title={<div><b>{t(`compare.${c.title}`)}</b><div style={{ fontSize: 12, fontWeight: 400, color: "var(--color-text-3)" }}>{t(`compare.${c.sub}`)}</div></div>}
>
                    <Statistic title={t("compare.dailyCost")} value={Math.round(col.cost)} groupSeparator prefix={<span style={{ fontSize: 14 }}>{symbol}</span>} />
                    {col.cost_std !== undefined && (
                      <Typography.Text type="secondary" style={{ fontSize: 12 }}>{t("compare.spread", { n: col.seeds })} ({num(col.cost_std, lang)})</Typography.Text>
                    )}
                    {c0 && c.key !== "C0" && (
                      <div style={{ marginTop: 8, fontSize: 18 }} className="good">{delta(col.vs_traditional_pct ?? 0, lang)} <span style={{ fontSize: 12, fontWeight: 400 }}>{t("compare.vsTraditional")}</span></div>
                    )}
                    {(c.key === "M2" || c.key === "M3") && (
                      <div style={{ fontSize: 13 }} className="good">{delta(col.vs_manual_pct, lang)} <span style={{ fontWeight: 400, color: "var(--color-text-3)" }}>{t("compare.vsManualShort")}</span></div>
                    )}
                    <div style={{ marginTop: 10, fontSize: 13, lineHeight: 2 }}>
                      <div>{t("compare.unfinished")}: <b className={col.unfinished > 0 ? "bad" : ""}>{col.unfinished}</b></div>
                      <div>{t("compare.km")}: <b>{num(col.km, lang)}</b></div>
                      <div>{t("compare.hitRate")}: <b>{pct(col.on_time_rate, lang)}</b></div>
                      {c.key === "C0" && col.wait_hours !== undefined && <div>{t("compare.waitHours")}: <b className="bad">{num(col.wait_hours, lang)}</b></div>}
                      <div>{t("compare.runtime")}: <b>{c.key === "H0" || c.key === "C0" ? t("common.none") : col.budget_s ? `${num(col.budget_s, lang)} ${t("common.seconds")}` : `${num(col.runtime_s, lang, 1)} ${t("common.seconds")}`}</b></div>
                      {c.key !== "C0" && c0 && (
                        <>
                          <div>{t("compare.savePerDay")}: <b className="good">{money(saved, cur, lang)}</b></div>
                          <div>{t("compare.saveYear")}: <b className="good">{money(saved * days, cur, lang)}</b></div>
                        </>
                      )}
                    </div>
                  </Card>
                </Col>
              );
            })}
          </Row>
          <Space wrap>
            <span>{t("compare.daysPerYear")}</span>
            <InputNumber size="small" min={1} max={366} value={days} onChange={(v) => setDays(Number(v) || 300)} style={{ width: 90 }} />
            <Tag size="small">{t("common.currencyNote")}</Tag>
          </Space>
          <Row gutter={12}>
            <Col xs={24} lg={14} style={{ marginBottom: 12 }}><Card title={t("compare.storyTitle")}><EChart option={story} height={260} /></Card></Col>
            {q.data.min_tractors && (
              <Col xs={24} lg={10} style={{ marginBottom: 12 }}>
                <Card title={t("compare.fleetTitle")}><EChart option={fleet} height={200} /><Typography.Text type="secondary" style={{ fontSize: 12 }}>{t("compare.fleetNote")}</Typography.Text></Card>
              </Col>
            )}
          </Row>
          <Alert type="info" content={t("compare.simulatedNote")} />
          <Card title={t("compare.curveTitle")}><EChart option={curve} height={220} /></Card>

          <Collapse defaultActiveKey={["how"]}>
            <Collapse.Item header={t("compare.howTitle")} name="how">
              <Row gutter={12}>
                {COLS.map((c) => (
                  <Col key={c.key} xs={24} md={12} xl={6} style={{ marginBottom: 8 }}>
                    <Card size="small" className="method-card" title={t(`compare.${c.title}`)}>
                      <p><b>{t("compare.how")}:</b> {t(`compare.${c.how}How`)}</p>
                      <p><b className="good">{t("compare.pros")}:</b> {t(`compare.${c.how}Pros`)}</p>
                      <p><b className="bad">{t("compare.cons")}:</b> {t(`compare.${c.how}Cons`)}</p>
                      <p><b>{t("compare.when")}:</b> {t(`compare.${c.how}When`)}</p>
                    </Card>
                  </Col>
                ))}
              </Row>
            </Collapse.Item>
            <Collapse.Item header={t("compare.moreMethods")} name="adv">
              <Table size="small" pagination={false} scroll={{ x: 560 }} rowKey="method" columns={[
                { title: "", dataIndex: "name" }, { title: t("compare.dailyCost"), dataIndex: "cost", align: "right" },
                { title: t("compare.vsTraditional"), dataIndex: "vs", align: "right" }, { title: t("compare.km"), dataIndex: "km", align: "right" },
                { title: t("compare.hitRate"), dataIndex: "hit", align: "right" }, { title: "", dataIndex: "desc" },
              ]} data={(q.data.advanced ?? []).map((a) => ({
                method: a.method, name: <span style={{ whiteSpace: "nowrap" }}>{t(a.method === "M0-R" ? "compare.m0r" : "compare.m1")}</span>,
                cost: <span style={{ whiteSpace: "nowrap" }}>{money(a.cost, cur, lang)}</span>,
                vs: <span style={{ whiteSpace: "nowrap" }}>{delta(((a.cost / base.cost) - 1) * 100, lang)}</span>, km: num(a.km, lang), hit: pct(a.on_time_rate, lang),
                desc: t(a.method === "M0-R" ? "compare.m0rDesc" : "compare.m1Desc"),
              }))} />
              <Card size="small" title={t("compare.exact")} style={{ marginTop: 12 }}>
                <p>{t("compare.exactDesc")}</p>
                <Typography.Text type="secondary">{t("compare.scalingTitle")}</Typography.Text>
                <Table size="small" pagination={false} scroll={{ x: 480 }} rowKey="n" columns={[
                  { title: t("compare.tasks"), dataIndex: "n" },
                  {
                    title: t("compare.exactTime"), dataIndex: "res",
                    render: (_: unknown, r: { proven: number; total: number; time: number }) =>
                      r.proven === r.total ? <Tag color="green">{t("compare.proven")} · {num(r.time, lang, 1)} {t("common.seconds")}</Tag>
                        : r.proven > 0 ? <Tag color="orange">{r.proven}/{r.total} {t("compare.proven")}</Tag>
                          : <Tag color="red">{t("compare.notProven", { s: scaling.data?.limit_s ?? 60 })}</Tag>,
                  },
                ]} data={scalingRows} />
                <p style={{ marginTop: 8 }}>{t("compare.exactResult")}</p>
              </Card>
            </Collapse.Item>
            <Collapse.Item header={t("compare.glossaryTitle")} name="gloss">
              <ul style={{ paddingLeft: 18, lineHeight: 1.9, margin: 0 }}>
                {["gCost", "gKm", "gHit", "gUnfinished", "gRuntime", "gVs", "gSpread", "gWait", "gFleet"].map((k) => <li key={k}>{t(`compare.${k}`)}</li>)}
              </ul>
            </Collapse.Item>
          </Collapse>
          <Space><Button type="primary" onClick={() => nav("/plan")}>{t("nav.plan")}</Button></Space>
        </>
      )}
    </Space>
  );
}
