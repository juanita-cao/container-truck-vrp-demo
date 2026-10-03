import { Alert, Button, Card, Grid, Input, InputNumber, Message, Select, Space, Table, TimePicker, Typography } from "@arco-design/web-react";
import { IconDelete, IconPlus } from "@arco-design/web-react/icon";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import dayjs from "dayjs";
import { useEffect, useMemo, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";
import { ApiError, get, http, type InstanceSummary } from "../api/client";
import { clock } from "../lib/format";
import { usePrefs } from "../state/prefs";

const { Row, Col } = Grid;

interface Net {
  hub: { name_en: string; name_zh: string };
  yards: { id: number; name_en: string; name_zh: string }[];
  clients: { id: number; code: string; area: string }[];
  limits: Record<string, [number, number]>;
  defaults: { speed_kmh: number; handling_min: number; service_range_min: [number, number]; pickup_width_min: number };
}
interface Job { key: number; client_id: number | null; kind: "import" | "export"; delivery_early: number; delivery_late: number; service_min: number; pickup_width: number }
interface Editable { tractors: number; tc_stock: number[]; speed_kmh: number; jobs: Omit<Job, "key">[]; label?: string }
interface ErrItem { code: string; job?: number; [k: string]: unknown }

const base8 = () => dayjs().startOf("day").hour(8).minute(0).second(0);
const toDay = (m: number) => base8().add(m, "minute");
const toMin = (d: dayjs.Dayjs) => d.diff(base8(), "minute");

export function InputPage() {
  const { t, i18n } = useTranslation();
  const p = usePrefs();
  const nav = useNavigate();
  const qc = useQueryClient();
  const net = useQuery({ queryKey: ["network", p.dataset], queryFn: () => get<Net>("/network", { dataset: p.dataset }) });
  const insts = useQuery({ queryKey: ["instances", p.dataset], queryFn: () => get<InstanceSummary[]>("/instances", { dataset: p.dataset }) });

  const [source, setSource] = useState<string | null>(null);          // 当前表单来自哪一天/哪个场景
  const [label, setLabel] = useState("My day");
  const [tractors, setTractors] = useState(16);
  const [stock, setStock] = useState<number[]>([]);
  const [speed, setSpeed] = useState(35);
  const [jobs, setJobs] = useState<Job[]>([]);
  const [errors, setErrors] = useState<ErrItem[]>([]);
  const [saved, setSaved] = useState<string | null>(null);
  const seq = useRef(1);

  const editingScenario = !!source && source.startsWith("my_");
  const mkJobs = (js: Editable["jobs"]): Job[] => js.map((j) => ({ ...j, key: seq.current++ }));

  async function loadFrom(name: string) {
    const v = await get<Editable & { label?: string }>(`/instances/${name}/jobs`, { dataset: p.dataset });
    setSource(name);
    setTractors(v.tractors); setStock(v.tc_stock); setSpeed(v.speed_kmh); setJobs(mkJobs(v.jobs)); setErrors([]); setSaved(null);
    setLabel(name.startsWith("my_") ? (v.label ?? name) : (label === "My day" || !label ? "My day" : label));
  }
  // 进入页面时，用当前选中的那一天（或场景）预填
  const first = useRef(true);
  useEffect(() => {
    if (first.current && p.instance && net.data) { first.current = false; loadFrom(p.instance).catch(() => undefined); }
  }, [p.instance, net.data]);   // eslint-disable-line react-hooks/exhaustive-deps

  const clientOptions = useMemo(() => (net.data?.clients ?? []).map((c) => ({ value: c.id, label: `${c.code} · ${c.area}` })), [net.data]);
  const yardName = (y: { name_en: string; name_zh: string }) => (i18n.language === "zh" ? y.name_zh.replace(" 挂车场", "") : y.name_en.replace(" yard", ""));
  const setJob = (key: number, patch: Partial<Job>) => setJobs((cur) => cur.map((j) => (j.key === key ? { ...j, ...patch } : j)));

  function addJob() {
    const c = net.data?.clients[0]?.id ?? null;
    setJobs((cur) => [...cur, { key: seq.current++, client_id: c, kind: "import", delivery_early: 60, delivery_late: 120, service_min: 120, pickup_width: net.data?.defaults.pickup_width_min ?? 90 }]);
  }
  function addRandom() {
    if (!net.data) return;
    const [lo, hi] = net.data.defaults.service_range_min;
    const add: Job[] = [];
    for (let i = 0; i < 10; i++) {
      const service = lo + Math.floor(Math.random() * (hi - lo + 1));
      const early = Math.floor(Math.random() * Math.max(1, 640 - service));
      const width = [30, 45, 60, 90][Math.floor(Math.random() * 4)];
      add.push({ key: seq.current++, client_id: net.data.clients[Math.floor(Math.random() * net.data.clients.length)].id, kind: Math.random() < 0.5 ? "import" : "export",
        delivery_early: early, delivery_late: Math.min(720, early + width), service_min: service, pickup_width: net.data.defaults.pickup_width_min });
    }
    setJobs((cur) => [...cur, ...add]);
  }

  async function save() {
    setErrors([]); setSaved(null);
    const body = { base: source && !source.startsWith("my_") ? source : "sg_mon", label: label.trim() || "My day", tractors, tc_stock: stock, speed_kmh: speed,
      jobs: jobs.map(({ key: _k, ...j }) => j) };
    try {
      const r = editingScenario
        ? await http.put(`/scenarios/${source}`, body, { params: { dataset: p.dataset } })
        : await http.post("/scenarios", body, { params: { dataset: p.dataset } });
      const name: string = r.data.name;
      await qc.invalidateQueries({ queryKey: ["instances"] });
      p.setInstance(name); setSource(name); setSaved(name);
      Message.success(t("input.saved"));
    } catch (e) {
      if (e instanceof ApiError && e.code === "SCENARIO_INVALID") setErrors((e.params.errors as ErrItem[]) ?? []);
      else setErrors([{ code: e instanceof ApiError ? e.code : "UNKNOWN" }]);
    }
  }
  async function remove() {
    if (!source || !editingScenario) return;
    await http.delete(`/scenarios/${source}`, { params: { dataset: p.dataset } });
    await qc.invalidateQueries({ queryKey: ["instances"] });
    Message.success(t("input.deleted"));
    first.current = true; setSource(null); p.setInstance("sg_mon"); setSaved(null);
    loadFrom("sg_mon").catch(() => undefined);
  }

  const errText = (e: ErrItem) => (i18n.exists(`errors.${e.code}`) ? t(`errors.${e.code}`, e as Record<string, unknown>) : t("errors.UNKNOWN"));
  const days = (insts.data ?? []).filter((i) => !i.meta.scenario);
  const mine = (insts.data ?? []).filter((i) => i.meta.scenario);
  const lim = net.data?.limits;
  const tasks = jobs.length * 2;
  const errJobs = new Set(errors.filter((e) => e.job).map((e) => e.job as number));

  return (
    <Space direction="vertical" size="medium" style={{ width: "100%" }}>
      <div>
        <Typography.Title heading={4} className="page-title">{t("input.title")}</Typography.Title>
        <Typography.Text type="secondary">{t("input.subtitle")}</Typography.Text>
      </div>
      <Card size="small">
        <Space wrap size="medium">
          <span>{t("input.startFrom")}</span>
          <Select style={{ width: 280 }} value={source ?? undefined} onChange={(v) => loadFrom(v)} loading={insts.isLoading}>
            <Select.OptGroup label={t("input.templates")}>{days.map((i) => <Select.Option key={i.name} value={i.name}>{`${t(`days.${i.meta.day}`)} · ${i.tasks / 2} / ${i.tractors}`}</Select.Option>)}</Select.OptGroup>
            {mine.length > 0 && <Select.OptGroup label={t("input.mine")}>{mine.map((i) => <Select.Option key={i.name} value={i.name}>{`★ ${i.meta.label ?? i.name}`}</Select.Option>)}</Select.OptGroup>}
          </Select>
          <Input style={{ width: 240 }} value={label} onChange={setLabel} addBefore={t("input.label")} maxLength={60} />
          <Button type="primary" onClick={save} disabled={jobs.length === 0}>{editingScenario ? t("input.update") : t("input.save")}</Button>
          {editingScenario && <Button status="danger" icon={<IconDelete />} onClick={remove}>{t("input.remove")}</Button>}
        </Space>
      </Card>

      {errors.length > 0 && <Alert type="error" title={t("input.problems")} content={<ul style={{ margin: 0, paddingLeft: 18 }}>{errors.slice(0, 12).map((e, i) => <li key={i}>{errText(e)}</li>)}</ul>} />}
      {saved && (
        <Alert type="success" title={t("input.saved")} content={
          <Space wrap><span>{t("input.next")}</span>
            <Button size="small" type="primary" onClick={() => nav("/plan")}>{t("input.planNow")}</Button>
            <Button size="small" onClick={() => nav("/compare")}>{t("input.seeCompare")}</Button></Space>} />
      )}

      <Row gutter={12}>
        <Col xs={24} lg={12} style={{ marginBottom: 12 }}>
          <Card title={t("input.fleetTitle")} className="method-card">
            <Space direction="vertical" size="small" style={{ width: "100%" }}>
              <Space>{t("input.tractors")}<InputNumber min={lim?.tractors[0] ?? 1} max={lim?.tractors[1] ?? 60} value={tractors} onChange={(v) => setTractors(Number(v) || 1)} style={{ width: 110 }} /></Space>
              {(net.data?.yards ?? []).map((y, i) => (
                <Space key={y.id}>{t("input.yardStock", { yard: yardName(y) })}
                  <InputNumber min={lim?.tc_stock[0] ?? 0} max={lim?.tc_stock[1] ?? 100} value={stock[i] ?? 0} style={{ width: 90 }}
                    onChange={(v) => setStock((cur) => cur.map((x, k) => (k === i ? Number(v) || 0 : x)))} /></Space>
              ))}
              <Space>{t("input.speed")}<InputNumber min={lim?.speed[0] ?? 10} max={lim?.speed[1] ?? 90} value={speed} onChange={(v) => setSpeed(Number(v) || 35)} style={{ width: 110 }} /></Space>
            </Space>
          </Card>
        </Col>
        <Col xs={24} lg={12} style={{ marginBottom: 12 }}>
          <Card title={t("input.howTitle")} className="method-card">
            <ul style={{ paddingLeft: 18, lineHeight: 1.9, margin: 0 }}><li>{t("input.how1")}</li><li>{t("input.how2")}</li><li>{t("input.how3")}</li></ul>
            <Alert style={{ marginTop: 10 }} type="info" content={t("input.masterData")} />
          </Card>
        </Col>
      </Row>

      <Card title={t("input.jobsTitle")} extra={<Typography.Text type="secondary">{t("input.summary", { jobs: jobs.length, tasks, tractors })}</Typography.Text>}>
        <Space style={{ marginBottom: 10 }}>
          <Button type="primary" icon={<IconPlus />} onClick={addJob}>{t("input.addJob")}</Button>
          <Button onClick={addRandom}>{t("input.addRandom")}</Button>
          <Button status="danger" onClick={() => setJobs([])} disabled={jobs.length === 0}>{t("input.clear")}</Button>
        </Space>
        <Table size="small" rowKey="key" pagination={{ pageSize: 10, sizeCanChange: false }} scroll={{ x: 1040 }}
          rowClassName={(r: Job) => (errJobs.has(jobs.findIndex((j) => j.key === r.key) + 1) ? "row-error" : "")}
          columns={[
            { title: t("input.cNo"), width: 56, render: (_: unknown, r: Job) => jobs.findIndex((j) => j.key === r.key) + 1 },
            { title: t("input.cCustomer"), width: 220, render: (_: unknown, r: Job) => (
              <Select showSearch size="small" style={{ width: 200 }} value={r.client_id ?? undefined} placeholder={t("input.chooseCustomer")} options={clientOptions}
                onChange={(v) => setJob(r.key, { client_id: v })} filterOption={(q, o) => String((o as { props: { children: string } }).props.children).toLowerCase().includes(q.toLowerCase())} />) },
            { title: t("input.cType"), width: 230, render: (_: unknown, r: Job) => (
              <Select size="small" style={{ width: 210 }} value={r.kind} onChange={(v) => setJob(r.key, { kind: v })}
                options={[{ value: "import", label: t("input.kindImport") }, { value: "export", label: t("input.kindExport") }]} />) },
            { title: t("input.cFrom"), width: 115, render: (_: unknown, r: Job) => (
              <TimePicker size="small" format="HH:mm" allowClear={false} style={{ width: 100 }} value={toDay(r.delivery_early)} disabledHours={() => [...Array(8).keys(), ...[20, 21, 22, 23]]}
                onChange={(_s, d) => d && setJob(r.key, { delivery_early: toMin(d) })} />) },
            { title: t("input.cTo"), width: 115, render: (_: unknown, r: Job) => (
              <TimePicker size="small" format="HH:mm" allowClear={false} style={{ width: 100 }} value={toDay(r.delivery_late)} disabledHours={() => [...Array(8).keys(), ...[21, 22, 23]]}
                onChange={(_s, d) => d && setJob(r.key, { delivery_late: toMin(d) })} />) },
            { title: <span title={t("input.handlingHelp")}>{t("input.cHandling")} ⓘ</span>, width: 150, render: (_: unknown, r: Job) => (
              <InputNumber size="small" min={lim?.service[0] ?? 15} max={lim?.service[1] ?? 600} step={15} value={r.service_min} style={{ width: 100 }}
                onChange={(v) => setJob(r.key, { service_min: Number(v) || 60 })} />) },
            { title: <span title={t("input.pickupHelp")}>{t("input.cPickup")} ⓘ</span>, width: 140, render: (_: unknown, r: Job) => `${clock(r.delivery_early + r.service_min)}–${clock(r.delivery_early + r.service_min + r.pickup_width)}` },
            { title: t("input.cRemove"), width: 70, render: (_: unknown, r: Job) => <Button size="mini" status="danger" icon={<IconDelete />} aria-label={t("input.cRemove")} onClick={() => setJobs((cur) => cur.filter((j) => j.key !== r.key))} /> },
          ]} data={jobs} />
      </Card>
    </Space>
  );
}
