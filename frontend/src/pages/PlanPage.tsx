import { Alert, Button, Card, Collapse, Descriptions, Grid, InputNumber, Progress, Select, Space, Statistic, Table, Tag, Typography } from "@arco-design/web-react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";
import { ApiError, get, http, type CompareResp, type RunRecord } from "../api/client";
import { ErrorNote } from "../components/ErrorNote";
import { delta, money, num, pct } from "../lib/format";
import { usePrefs } from "../state/prefs";

const { Row, Col } = Grid;
const BUDGETS = [10, 60, 300];
const METHODS = ["M0-R", "M1", "M2", "M3", "H0"];

export function PlanPage() {
  const { t } = useTranslation();
  const p = usePrefs();
  const nav = useNavigate();
  const qc = useQueryClient();
  const [budget, setBudget] = useState(60);
  const [method, setMethod] = useState("M0-R");
  const [seed, setSeed] = useState(0);
  const [runId, setRunId] = useState<string | null>(null);
  const [run, setRun] = useState<RunRecord | null>(null);
  const [error, setError] = useState<unknown>(null);
  const timer = useRef<number | null>(null);
  const lang = p.lang;

  const compare = useQuery({
    queryKey: ["compare", p.dataset, p.instance], enabled: !!p.instance, retry: false,
    queryFn: () => get<CompareResp>("/compare", { instance: p.instance, dataset: p.dataset }),
  });
  const manualCost = compare.data?.columns.find((c) => c.method === "H0")?.cost;

  const stopPolling = () => { if (timer.current) window.clearInterval(timer.current); timer.current = null; };
  useEffect(() => stopPolling, []);

  async function start(body: Record<string, unknown>) {
    setError(null); setRun(null); stopPolling();
    try {
      const r = await http.post<{ run_id: string; method: string }>("/solve", { dataset: p.dataset, instance: p.instance, ...body });
      setRunId(r.data.run_id);
      timer.current = window.setInterval(async () => {
        try {
          const s = await get<RunRecord>(`/runs/${r.data.run_id}`);
          setRun(s);
          if (!["QUEUED", "RUNNING"].includes(s.status)) {
            stopPolling();
            if (s.verified) { p.addRecent({ run_id: s.run_id, instance: s.instance, dataset: s.dataset, method: s.method, at: new Date().toISOString() }); qc.invalidateQueries({ queryKey: ["runs"] }); }
          }
        } catch (e) { setError(e); stopPolling(); }
      }, 400);
    } catch (e) { setError(e instanceof ApiError ? e : new ApiError("UNKNOWN")); }
  }
  async function stop() { if (runId) { try { await http.post(`/runs/${runId}/cancel`); } catch { /* 已结束 */ } } }

  if (!p.instance) return <Alert type="info" content={t("plan.noInstance")} />;
  const running = !!run && ["QUEUED", "RUNNING"].includes(run.status);
  const busy = !!runId && (!run || running);
  const cur = run?.currency ?? "CNY";

  return (
    <Space direction="vertical" size="medium" style={{ width: "100%" }}>
      <div>
        <Typography.Title heading={4} className="page-title">{t("plan.title")}</Typography.Title>
        <Typography.Text type="secondary">{t("plan.subtitle")}</Typography.Text>
      </div>
      <Row gutter={12}>
        <Col xs={24} md={12} style={{ marginBottom: 12 }}>
          <Card className="method-card" title={<b>{t("plan.nowTitle")}</b>} style={{ borderTop: "3px solid #165dff" }}>
            <p>{t("plan.nowDesc")}</p>
            <Typography.Text type="secondary">{t("plan.nowScene")}</Typography.Text>
            <div style={{ marginTop: 14 }}><Button type="primary" disabled={busy} onClick={() => start({ mode: "now" })}>{t("plan.nowButton")}</Button></div>
          </Card>
        </Col>
        <Col xs={24} md={12} style={{ marginBottom: 12 }}>
          <Card className="method-card" title={<b>{t("plan.tomorrowTitle")}</b>} style={{ borderTop: "3px solid #00b42a" }}>
            <p>{t("plan.tomorrowDesc")}</p>
            <Typography.Text type="secondary">{t("plan.tomorrowScene")}</Typography.Text>
            <div style={{ marginTop: 14 }}>
              <Space wrap>
                <Select size="small" style={{ width: 170 }} value={budget} onChange={setBudget} addBefore={t("plan.budget")}
                  options={BUDGETS.map((b) => ({ value: b, label: `${b} ${t("common.seconds")}` }))} />
                <Button type="primary" status="success" disabled={busy} onClick={() => start({ mode: "tomorrow", budget_s: budget })}>{t("plan.tomorrowButton")}</Button>
              </Space>
              <div style={{ marginTop: 6, fontSize: 12, color: "var(--color-text-3)" }}>{t("plan.budgetHelp")}</div>
            </div>
          </Card>
        </Col>
      </Row>
      <Collapse>
        <Collapse.Item header={t("plan.advanced")} name="adv">
          <Space wrap>
            <Select size="small" style={{ width: 200 }} value={method} onChange={setMethod} addBefore={t("plan.method")} options={METHODS.map((m) => ({ value: m, label: m }))} />
            <InputNumber size="small" min={0} value={seed} onChange={(v) => setSeed(Number(v) || 0)} style={{ width: 130 }} prefix={t("plan.seed")} />
            <Button size="small" disabled={busy} onClick={() => start({ method, seed, budget_s: method === "M3" ? budget : undefined })}>{t("common.run")}</Button>
          </Space>
        </Collapse.Item>
      </Collapse>

      {error ? <ErrorNote error={error} /> : null}
      {run && (
        <Card title={<Space>{t("plan.result")}<Tag color={run.status === "DONE" ? "green" : run.status === "RUNNING" || run.status === "QUEUED" ? "arcoblue" : "orange"}>{t(`plan.status.${run.status}`, run.status)}</Tag>{run.method && <Tag>{run.method}</Tag>}</Space>}>
          {running && (
            <Space direction="vertical" style={{ width: "100%" }}>
              <Progress percent={run.progress ? Math.min(99, Math.round((run.progress.elapsed_s / (budget || 60)) * 100)) : 0} status="normal" />
              {run.progress && <span>{t("plan.progress")}: <b>{money(run.progress.best_cost, cur, lang)}</b> · {run.progress.iterations} {t("plan.iterations")}</span>}
              <Button size="small" onClick={stop}>{t("plan.stop")}</Button>
            </Space>
          )}
          {run.error && <ErrorNote error={new ApiError(run.error.code)} />}
          {run.cost && (
            <Space direction="vertical" size="medium" style={{ width: "100%" }}>
              <Row gutter={12} className="kpi-grid">
                <Col xs={12} md={6}><Statistic title={t("plan.dailyCost")} value={Math.round(run.cost.total)} groupSeparator prefix={money(0, cur, lang).replace(/[\d\s.,]/g, "")} /></Col>
                <Col xs={12} md={6}>
                  <div className="arco-statistic-title" style={{ color: "var(--color-text-2)", fontSize: 14 }}>{t("plan.vsManual")}</div>
                  <div style={{ fontSize: 26, fontWeight: 600 }} className="good">{manualCost ? delta((run.cost.total / manualCost - 1) * 100, lang) : t("common.none")}</div>
                </Col>
                <Col xs={12} md={6}><Statistic title={t("plan.km")} value={run.totals.mileage_km} groupSeparator precision={0} /></Col>
                <Col xs={12} md={6}><Statistic title={t("plan.hitRate")} value={run.verified.on_time_rate !== null ? pct(run.verified.on_time_rate, lang) : "—"} /></Col>
              </Row>
              <Descriptions column={{ xs: 1, md: 3 }} size="small" data={[
                { label: t("plan.unfinished"), value: String(run.totals.unfinished) },
                { label: t("plan.tractorsUsed"), value: `${run.verified.tractors_used} / ${run.tractors}` },
                { label: t("compare.runtime"), value: `${num(run.runtime_s, lang, 1)} ${t("common.seconds")}` },
              ]} />
              <Table size="small" pagination={false} rowKey="k" columns={[{ title: t("plan.costBreakdown"), dataIndex: "label" }, { title: "", dataIndex: "v", align: "right" }]} data={[
                { k: "fuel", label: t("plan.fuel"), v: money(run.cost.fuel, cur, lang) }, { k: "driver", label: t("plan.driver"), v: money(run.cost.driver, cur, lang) },
                { k: "fixed", label: t("plan.fixed"), v: money(run.cost.tractor_fixed + run.cost.trailer_fixed, cur, lang) },
                { k: "outsource", label: t("plan.outsource"), v: money(run.cost.outsource, cur, lang) }, { k: "penalty", label: t("plan.penalty"), v: money(run.cost.penalty, cur, lang) },
              ]} />
              {run.verified.feasible
                ? <Tag color="green">{t("plan.feasible")}</Tag>
                : <Alert type="error" title={t("plan.violations")} content={run.verified.violations.map((v) => t(`errors.${v.code}`, t("errors.VIOLATION"))).join(" · ")} />}
              {run.status === "DONE" || run.status === "CANCELLED" ? <Button type="primary" onClick={() => nav(`/replay?run=${run.run_id}`)}>{t("plan.openReplay")}</Button> : null}
            </Space>
          )}
        </Card>
      )}
      {p.recent.length > 0 && (
        <Card size="small" title={t("plan.recent")}>
          <Space wrap>{p.recent.slice(0, 8).map((r) => <Tag key={r.run_id} style={{ cursor: "pointer" }} onClick={() => nav(`/replay?run=${r.run_id}`)}>{r.instance} · {r.method}</Tag>)}</Space>
        </Card>
      )}
    </Space>
  );
}
