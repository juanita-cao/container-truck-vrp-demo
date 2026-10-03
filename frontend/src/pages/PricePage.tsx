import { Alert, Button, Card, Form, InputNumber, Message, Select, Space, Tag, Typography } from "@arco-design/web-react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { get, http, type PriceTable } from "../api/client";
import { usePrefs } from "../state/prefs";
import { ErrorNote } from "../components/ErrorNote";

const FIELDS = [
  { k: "fuel_l_per_100km", label: "fuelPer100" }, { k: "fuel_price_per_l", label: "fuelPrice" }, { k: "driver_per_hour", label: "driver" },
  { k: "tractor_fixed_per_day", label: "tractorFixed" }, { k: "trailer_fixed_per_day", label: "trailerFixed" },
  { k: "outsource_per_task", label: "outsource" }, { k: "penalty_per_minute", label: "penalty" },
] as const;

export function PricePage() {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const p = usePrefs();
  const q = useQuery({ queryKey: ["price", p.dataset], queryFn: () => get<PriceTable>("/price-table", { dataset: p.dataset }) });
  const [form, setForm] = useState<Record<string, number | string>>({});
  useEffect(() => { if (q.data) setForm({ ...q.data } as unknown as Record<string, number | string>); }, [q.data]);

  async function save() {
    const body: Record<string, unknown> = { currency: form.currency };
    FIELDS.forEach((f) => (body[f.k] = Number(form[f.k])));
    await http.put("/price-table", body, { params: { dataset: p.dataset } });
    await qc.invalidateQueries();
    Message.success(t("price.saved"));
  }
  const srcTag = (k: string) => {
    const s = q.data?.sources?.[k] ?? "fictional";
    return <Tag size="small" color={s === "edited" ? "green" : "orangered"}>{s === "edited" ? t("price.srcEdited") : t("price.srcFictional")}</Tag>;
  };

  return (
    <Space direction="vertical" size="medium" style={{ width: "100%" }}>
      <div>
        <Typography.Title heading={4} className="page-title">{t("price.title")}</Typography.Title>
        <Typography.Text type="secondary">{t("price.subtitle")}</Typography.Text>
      </div>
      {q.isError && <ErrorNote error={q.error} onRetry={() => q.refetch()} />}
      {q.data && (
        <Card title={<Space>{t("price.version")}<Tag>{q.data.current}</Tag></Space>} extra={<Space>{t("price.versions")}: {q.data.versions.map((v) => <Tag key={v} size="small">{v}</Tag>)}</Space>}>
          <Form layout="vertical" style={{ maxWidth: 560 }}>
            <Form.Item label={t("price.currency")}>
              <Select value={String(form.currency)} onChange={(v) => setForm({ ...form, currency: v })} style={{ width: 140 }} options={["CNY", "SGD", "USD"].map((c) => ({ value: c, label: c }))} />
            </Form.Item>
            {FIELDS.map((f) => (
              <Form.Item key={f.k} label={<Space>{t(`price.${f.label}`)}{srcTag(f.k)}</Space>}>
                <InputNumber min={0} value={Number(form[f.k] ?? 0)} onChange={(v) => setForm({ ...form, [f.k]: Number(v) || 0 })} style={{ width: 180 }} />
              </Form.Item>
            ))}
            <Button type="primary" onClick={save}>{t("common.save")}</Button>
          </Form>
          <Alert style={{ marginTop: 16 }} type="info" content={t("price.note")} />
          <Alert style={{ marginTop: 8 }} type="info" content={t("price.penaltyNote")} />
        </Card>
      )}
    </Space>
  );
}
