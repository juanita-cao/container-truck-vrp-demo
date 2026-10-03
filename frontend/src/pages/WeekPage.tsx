import { Alert, Button, Card, Skeleton, Space, Table, Tag, Typography } from "@arco-design/web-react";
import { useQuery } from "@tanstack/react-query";
import { useMemo } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";
import { get, type WeekResp } from "../api/client";
import { EChart } from "../components/EChart";
import { ErrorNote } from "../components/ErrorNote";
import { delta, money, num } from "../lib/format";
import { usePrefs } from "../state/prefs";

export function WeekPage() {
  const { t } = useTranslation();
  const p = usePrefs();
  const nav = useNavigate();
  const q = useQuery({ queryKey: ["week", p.dataset], queryFn: () => get<WeekResp>("/week", { dataset: p.dataset }), enabled: p.dataset === "demo_sg" });

  const chart = useMemo(() => {
    const d = q.data?.days ?? [];
    return {
      tooltip: { trigger: "axis" as const }, legend: { data: [t("week.tasks"), t("week.onDuty")] },
      grid: { left: 44, right: 56, top: 44, bottom: 28 },
      xAxis: { type: "category" as const, data: d.map((x) => t(`days.${x.day}`)) },
      yAxis: [{ type: "value" as const, name: t("week.tasks") }, { type: "value" as const, name: t("week.onDuty") }],
      series: [
        { name: t("week.tasks"), type: "bar" as const, data: d.map((x) => x.tasks), itemStyle: { color: "#165dff" }, barMaxWidth: 36 },
        { name: t("week.onDuty"), type: "line" as const, yAxisIndex: 1, data: d.map((x) => x.tractors), itemStyle: { color: "#f77234" }, symbolSize: 8 },
      ],
    };
  }, [q.data, t]);

  if (p.dataset !== "demo_sg") return <Alert type="info" content={t("week.onlyDemo")} />;
  return (
    <Space direction="vertical" size="medium" style={{ width: "100%" }}>
      <div>
        <Typography.Title heading={4} className="page-title">{t("week.title")}</Typography.Title>
        <Typography.Text type="secondary">{t("week.subtitle")}</Typography.Text>
      </div>
      {q.isLoading && <Skeleton text={{ rows: 6 }} animation />}
      {q.isError && <ErrorNote error={q.error} onRetry={() => q.refetch()} />}
      {q.data && (() => {
        const w = q.data;
        const lang = p.lang;
        const saved = (w.week_total.C0 ?? w.week_total.H0).cost - w.week_total.M3.cost;
        return (
          <>
            <Card title={t("week.chartTitle")}><EChart option={chart} height={260} /></Card>
            <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(158px, 1fr))", gap: 12 }}>
              {w.days.map((d) => (
                <div key={d.day}>
                  <Card size="small" title={<Space>{t(`days.${d.day}`)}<Tag size="small">{d.tasks} {t("week.tasks").toLowerCase()}</Tag></Space>} bordered>
                    <div style={{ fontSize: 12, color: "var(--color-text-3)" }}>{t("week.onDuty")}: {d.tractors}</div>
                    {d.min_tractors && <div style={{ fontSize: 12, color: "var(--color-text-3)" }}>{t("week.fleetNeeded")}: {d.min_tractors.C0} → <b>{d.min_tractors.H0}</b></div>}
                    {(["C0", "H0", "M2", "M3"] as const).filter((m) => d.cost[m] !== undefined).map((m) => (
                      <div key={m} style={{ marginTop: 8 }}>
                        <div style={{ fontSize: 12, color: "var(--color-text-3)" }}>{t(m === "C0" ? "week.traditional" : m === "H0" ? "week.manual" : m === "M2" ? "week.now" : "week.tomorrow")}</div>
                        <div>
                          <b>{money(d.cost[m], w.currency, lang)}</b>
                          {m !== "C0" && d.cost.C0 !== undefined && <span className="good"> {delta((d.cost[m] / d.cost.C0 - 1) * 100, lang)}</span>}
                        </div>
                      </div>
                    ))}
                    <Button size="mini" long style={{ marginTop: 10 }} onClick={() => { p.setInstance(`sg_${d.day}`); nav("/compare"); }}>{t("week.openDay")}</Button>
                  </Card>
                </div>
              ))}
            </div>
            <Card title={t("week.weekTotal")}>
              <Table pagination={false} size="small" rowKey="m" columns={[
                { title: "", dataIndex: "label" },
                { title: t("week.dayCost"), dataIndex: "cost", align: "right" },
                { title: t("compare.vsTraditional"), dataIndex: "vs", align: "right" },
                { title: t("week.serveAll"), dataIndex: "serve", align: "right" },
              ]} data={(["C0", "H0", "M2", "M3"] as const).filter((m) => w.week_total[m]).map((m) => ({
                m, label: t(m === "C0" ? "week.traditional" : m === "H0" ? "week.manual" : m === "M2" ? "week.now" : "week.tomorrow"),
                cost: money(w.week_total[m].cost, w.currency, lang),
                vs: m === "C0" ? t("common.none") : <span className="good">{delta(w.week_total[m].vs_traditional_pct ?? w.week_total[m].vs_manual_pct, lang)}</span>,
                serve: w.serve_all_total?.[m] ? <span>{money(w.serve_all_total[m].cost, w.currency, lang)}{m !== "C0" && <span className="good"> {delta(w.serve_all_total[m].vs_traditional_pct, lang)}</span>}</span> : t("common.none"),
              }))} />
              <div style={{ marginTop: 8 }}>{t("week.savedWeek")}: <b className="good">{money(saved, w.currency, lang)}</b> <Typography.Text type="secondary">({num(saved * 52, lang)} / {t("common.perYear")}, {t("common.currencyNote")})</Typography.Text></div>
            </Card>
            <Alert type="warning" content={t("week.assumptionNote")} />
          </>
        );
      })()}
    </Space>
  );
}
