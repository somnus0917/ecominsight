import {
  AlertOctagon,
  Boxes,
  ChartNoAxesCombined,
  CircleDollarSign,
  LayoutDashboard,
  PackageSearch,
  Search,
  Store,
} from "lucide-react";
import type { ReactNode } from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "../api";
import { NavLink } from "../router";

const navigation = [
  { to: "/", label: "经营总览", icon: LayoutDashboard },
  { to: "/shops", label: "店铺分析", icon: Store },
  { to: "/products", label: "商品分析", icon: PackageSearch },
  { to: "/search", label: "搜索分析", icon: Search },
  { to: "/inventory", label: "库存分析", icon: Boxes },
  { to: "/finance", label: "财务结算", icon: CircleDollarSign },
  { to: "/anomalies", label: "异常中心", icon: AlertOctagon },
];

export function AppShell({ children }: { children: ReactNode }) {
  const health = useQuery({ queryKey: ["health"], queryFn: api.health });
  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand-block">
          <div className="brand-mark">
            <ChartNoAxesCombined size={21} />
          </div>
          <div>
            <strong>EcomInsight</strong>
            <span>Evidence Operations</span>
          </div>
        </div>
        <nav aria-label="主导航">
          {navigation.map(({ to, label, icon: Icon }) => (
            <NavLink
              key={to}
              to={to}
              end={to === "/"}
              className={({ isActive }) => (isActive ? "nav-item active" : "nav-item")}
            >
              <Icon size={17} strokeWidth={1.8} />
              <span>{label}</span>
            </NavLink>
          ))}
        </nav>
        <div className="sidebar-status">
          <div className="status-line">
            <span
              className={`status-dot ${health.data?.status === "ok" ? "online" : ""}`}
            />
            {health.data?.status === "ok" ? "本地仓库在线" : "正在连接"}
          </div>
          {health.data?.data_mode === "demo" && (
            <div className="demo-badge" title="当前使用合成演示数据">
              Synthetic Demo · 合成演示数据
            </div>
          )}
          <small>更新至 {health.data?.data_updated_at ?? "-"}</small>
          <small>外部模型默认关闭</small>
        </div>
      </aside>
      <main className="main-content">{children}</main>
    </div>
  );
}
