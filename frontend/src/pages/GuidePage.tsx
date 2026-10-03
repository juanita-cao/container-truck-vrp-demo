import { Button, Card, Collapse, Grid, Space, Typography } from "@arco-design/web-react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";

const { Row, Col } = Grid;
const STEPS = [
  { k: "s1", to: "/input" }, { k: "s2", to: "/plan" }, { k: "s3", to: "/replay" }, { k: "s4", to: "/compare" }, { k: "s5", to: "/price" },
] as const;
const CONCEPTS = ["Hub", "Yard", "Drop", "Trad", "Job", "Window", "Handling", "Now", "Fleet"] as const;

export function GuidePage() {
  const { t } = useTranslation();
  const nav = useNavigate();
  return (
    <Space direction="vertical" size="medium" style={{ width: "100%", maxWidth: 1000 }}>
      <div>
        <Typography.Title heading={4} className="page-title">{t("guide.title")}</Typography.Title>
        <Typography.Text type="secondary">{t("guide.subtitle")}</Typography.Text>
      </div>
      <Card title={t("guide.stepsTitle")}>
        <div style={{ display: "flex", flexDirection: "column", gap: 18 }}>
          {STEPS.map((s, i) => (
            <div key={s.k} style={{ display: "flex", gap: 14, alignItems: "flex-start" }}>
              <div style={{ flex: "0 0 30px", height: 30, borderRadius: "50%", background: "rgb(var(--arcoblue-6))", color: "#fff", display: "flex", alignItems: "center", justifyContent: "center", fontWeight: 600 }}>{i + 1}</div>
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ fontWeight: 600, fontSize: 15 }}>{t(`guide.${s.k}t`).replace(/^\d+\.\s*/, "")}</div>
                <div style={{ color: "var(--color-text-2)", lineHeight: 1.7, margin: "4px 0 8px" }}>{t(`guide.${s.k}d`)}</div>
                <Button size="small" type="outline" onClick={() => nav(s.to)}>{t("guide.go")}</Button>
              </div>
            </div>
          ))}
        </div>
      </Card>
      <Card title={t("guide.conceptsTitle")}>
        <Row gutter={[12, 12]}>
          {CONCEPTS.map((c) => (
            <Col key={c} xs={24} md={12}>
              <div style={{ lineHeight: 1.7 }}><b>{t(`guide.c${c}`)}</b><div style={{ color: "var(--color-text-2)" }}>{t(`guide.c${c}D`)}</div></div>
            </Col>
          ))}
        </Row>
      </Card>
      <Card title={t("guide.faqTitle")}>
        <Collapse bordered={false}>
          {[1, 2, 3, 4, 5, 6].map((n) => (
            <Collapse.Item key={n} name={String(n)} header={t(`guide.q${n}`)}><div style={{ lineHeight: 1.8 }}>{t(`guide.a${n}`)}</div></Collapse.Item>
          ))}
        </Collapse>
      </Card>
      <Card title={t("guide.limitsTitle")}>
        <ul style={{ paddingLeft: 18, lineHeight: 1.9, margin: 0 }}>{[1, 2, 3, 4].map((n) => <li key={n}>{t(`guide.l${n}`)}</li>)}</ul>
      </Card>
    </Space>
  );
}
