import { Avatar, Button, Drawer, Dropdown, Layout, Menu, Radio, Select, Space, Tag } from "@arco-design/web-react";
import { IconBook, IconCalendar, IconDashboard, IconEdit, IconMenu, IconMenuFold, IconMenuUnfold, IconPlayArrow, IconSettings, IconSwap, IconThunderbolt } from "@arco-design/web-react/icon";
import { useQuery } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { Navigate, Outlet, useLocation, useNavigate } from "react-router-dom";
import { get, type InstanceSummary } from "../api/client";
import { COPYRIGHT_OWNER, COPYRIGHT_YEAR } from "../config";
import { useNarrow } from "../lib/useNarrow";
import { usePrefs } from "../state/prefs";

const { Sider, Header, Content, Footer } = Layout;
const NAV = [
  { path: "/input", key: "input", icon: <IconEdit /> },
  { path: "/week", key: "week", icon: <IconCalendar /> },
  { path: "/compare", key: "compare", icon: <IconSwap /> },
  { path: "/plan", key: "plan", icon: <IconThunderbolt /> },
  { path: "/replay", key: "replay", icon: <IconPlayArrow /> },
  { path: "/price", key: "price", icon: <IconSettings /> },
  { path: "/guide", key: "guide", icon: <IconBook /> },
];

export function AppLayout() {
  const { t } = useTranslation();
  const p = usePrefs();
  const nav = useNavigate();
  const loc = useLocation();
  const [collapsed, setCollapsed] = useState(false);
  const [narrow, setNarrow] = useState(window.innerWidth < 1100);
  useEffect(() => { const f = () => setNarrow(window.innerWidth < 1100); window.addEventListener("resize", f); return () => window.removeEventListener("resize", f); }, []);
  const phone = useNarrow(768);
  const [drawer, setDrawer] = useState(false);
  const rail = collapsed || narrow;          // 窄屏强制折叠，但不改写用户的偏好（同 TCE）

  const instances = useQuery({ queryKey: ["instances", p.dataset], queryFn: () => get<InstanceSummary[]>("/instances", { dataset: p.dataset }) });
  useEffect(() => {
    if (instances.data?.length && (!p.instance || !instances.data.some((i) => i.name === p.instance))) p.setInstance(instances.data[0].name);
  }, [instances.data]);   // eslint-disable-line react-hooks/exhaustive-deps

  if (!p.company) return <Navigate to="/login" replace />;
  const selected = NAV.find((n) => loc.pathname.startsWith(n.path))?.path ?? "/input";
  const label = (i: InstanceSummary) => (i.meta.scenario ? `★ ${i.meta.label ?? i.name}` : i.meta.day ? `${t(`days.${i.meta.day}`)} · ${i.name}` : i.name);

  return (
    <Layout style={{ minHeight: "100vh" }}>
      {phone && (
        <Drawer visible={drawer} placement="left" width={240} title={<span className="brand-inline"><img src="/logo.svg" alt="" width={24} height={24} />{t("common.appName")}</span>}
          footer={null} onCancel={() => setDrawer(false)} bodyStyle={{ padding: 0 }}>
          <Menu selectedKeys={[selected]} onClickMenuItem={(k) => { setDrawer(false); nav(k); }} style={{ width: "100%" }}>
            {NAV.map((n) => <Menu.Item key={n.path}>{n.icon}{t(`nav.${n.key}`)}</Menu.Item>)}
          </Menu>
        </Drawer>
      )}
      {!phone && <Sider collapsed={rail} collapsible trigger={null} width={216} collapsedWidth={56} style={{ background: "var(--color-bg-2)", borderRight: "1px solid var(--color-border-2)" }}>
        <div className="brand"><img src="/logo.svg" alt="" width={28} height={28} style={{ flex: "0 0 28px" }} />{!rail && <span>{t("common.appName")}</span>}</div>
        <Menu selectedKeys={[selected]} onClickMenuItem={(k) => nav(k)} style={{ width: "100%" }}>
          {NAV.map((n) => <Menu.Item key={n.path}>{n.icon}{t(`nav.${n.key}`)}</Menu.Item>)}
        </Menu>
        {!narrow && (
          <Button type="text" className="collapse-btn" aria-label={collapsed ? t("nav.expand") : t("nav.collapse")}
            icon={collapsed ? <IconMenuUnfold /> : <IconMenuFold />} onClick={() => setCollapsed(!collapsed)} />
        )}
      </Sider>}
      <Layout>
        <Header className="topbar">
          <Space size={phone ? "mini" : "medium"} wrap={!phone} style={phone ? { flex: 1, minWidth: 0 } : undefined}>
            {phone && <Button type="text" aria-label={t("nav.menu")} icon={<IconMenu />} onClick={() => setDrawer(true)} />}
            <Select size="small" style={{ width: phone ? "calc(100vw - 190px)" : 230 }} value={p.instance ?? undefined} onChange={(v) => p.setInstance(v)} loading={instances.isLoading}
              addBefore={phone ? undefined : t("header.instance")} options={(instances.data ?? []).map((i) => ({ value: i.name, label: label(i) }))} />
          </Space>
          <Space size={phone ? "mini" : "medium"}>
            <Radio.Group type="button" size="small" value={p.lang} onChange={(v) => p.setLang(v)} aria-label={t("header.language")}
              options={[{ value: "en", label: "EN" }, { value: "zh", label: "中文" }]} />
            <Dropdown droplist={
              <Menu onClickMenuItem={(k) => { if (k === "logout" || k === "switch") { p.setCompany(null); nav("/login"); } }}>
                <Menu.Item key="switch">{t("header.switchCompany")}</Menu.Item>
                <Menu.Item key="logout">{t("header.logout")}</Menu.Item>
              </Menu>}>
              <Space style={{ cursor: "pointer" }}><Avatar size={28} style={{ backgroundColor: "#165dff" }}>B</Avatar>{!phone && <span>Bluewave</span>}</Space>
            </Dropdown>
          </Space>
        </Header>
        <Content className="content"><Outlet /></Content>
        <Footer className="statusbar">
          <span><Tag size="small" color="orangered">{t("common.fictional")}</Tag> {t("common.fictionalBanner")} · {t("common.dataBy")}</span>
          <span>© {COPYRIGHT_YEAR} {COPYRIGHT_OWNER}. {t("common.rights")}.</span>
        </Footer>
      </Layout>
    </Layout>
  );
}
export { IconDashboard };
