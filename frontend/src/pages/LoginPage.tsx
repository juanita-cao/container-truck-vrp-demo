import { Button, Card, Radio, Space, Typography } from "@arco-design/web-react";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Navigate, useNavigate } from "react-router-dom";
import { COPYRIGHT_OWNER, COPYRIGHT_YEAR } from "../config";
import { usePrefs } from "../state/prefs";

export function LoginPage() {
  const { t } = useTranslation();
  const p = usePrefs();
  const nav = useNavigate();
  const [company, setCompany] = useState("bluewave");
  if (p.company) return <Navigate to="/input" replace />;
  return (
    <div className="login">
      <Card style={{ width: 460 }}>
        <Space direction="vertical" size="large" style={{ width: "100%" }}>
          <div>
            <Space align="center" size="small"><img src="/logo.svg" alt="" width={40} height={40} /><Typography.Title heading={3} style={{ margin: 0 }}>{t("login.title")}</Typography.Title></Space>
            <Typography.Text type="secondary" style={{ display: "block", marginTop: 6 }}>{t("login.subtitle")}</Typography.Text>
          </div>
          <div>
            <div style={{ marginBottom: 8 }}>{t("login.company")}</div>
            <Radio.Group direction="vertical" value={company} onChange={setCompany}>
              <Radio value="bluewave">{t("login.bluewave")}</Radio>
            </Radio.Group>
          </div>
          <Button type="primary" long onClick={() => { p.setCompany(company); nav("/input"); }}>{t("login.enter")}</Button>
          <Typography.Text type="secondary" style={{ fontSize: 12 }}>{t("login.note")}</Typography.Text>
          <Radio.Group type="button" size="small" value={p.lang} onChange={(v) => p.setLang(v)} options={[{ value: "en", label: "EN" }, { value: "zh", label: "中文" }]} />
        </Space>
      </Card>
      <div style={{ position: "fixed", bottom: 12, left: 0, right: 0, textAlign: "center", fontSize: 12, color: "var(--color-text-3)" }}>
        © {COPYRIGHT_YEAR} {COPYRIGHT_OWNER}. {t("common.rights")}.
      </div>
    </div>
  );
}
