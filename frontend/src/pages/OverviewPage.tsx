import { useQuery } from "@tanstack/react-query";
import type { EChartsOption } from "echarts";
import { AlertTriangle, ArrowUpRight } from "lucide-react";
import { api } from "../api";
import { Chart } from "../components/Chart";
import { ErrorState, LoadingState } from "../components/States";
import { PageHeader, Panel } from "../components/Page";
import { integer, money } from "../format";
import { Link } from "../router";

export function OverviewPage() {
  const query = useQuery({ queryKey: ["overview"], queryFn: api.overview });
  if (query.isLoading) return <LoadingState />;
  if (query.error) return <ErrorState error={query.error} retry={() => query.refetch()} />;
  const data = query.data!;
  const trendOption: EChartsOption = {
    animationDuration: 450,
    tooltip: { trigger: "axis" },
    legend: { top: 0, right: 0, textStyle: { color: "#5d615f" } },
    grid: { left: 54, right: 28, top: 46, bottom: 38 },
    xAxis: {
      type: "category",
      data: data.trend.map((item) => item.date.slice(5)),
      axisLine: { lineStyle: { color: "#c8cbc5" } },
      axisLabel: { color: "#777b77" },
    },
    yAxis: {
      type: "value",
      splitLine: { lineStyle: { color: "#e8e7e1" } },
      axisLabel: { color: "#777b77" },
    },
    series: [
      {
        name: "支付金额",
        type: "line",
        smooth: 0.18,
        showSymbol: false,
        data: data.trend.map((item) => item.paid_amount),
        lineStyle: { width: 2.4, color: "#152b2a" },
        areaStyle: { color: "rgba(21,43,42,.08)" },
      },
      {
        name: "日报结算",
        type: "line",
        showSymbol: false,
        data: data.trend.map((item) => item.settlement_amount),
        lineStyle: { width: 1.5, color: "#d76b32" },
      },
    ],
  };
  return (
    <>
      <PageHeader
        eyebrow="Operations / 经营脉搏"
        title="跨平台经营总览"
        description="真实仓库聚合结果。金额、异常和结算均由程序计算，不经过大模型重算。"
        actions={
          <Link className="button-primary" to="/anomalies">
            查看异常中心 <ArrowUpRight size={15} />
          </Link>
        }
      />
      <div className="kpi-grid">
        {data.kpis.map((kpi) => (
          <article className={`kpi-card ${kpi.code === "anomaly_count" ? "signal" : ""}`} key={kpi.code}>
            <span>{kpi.label}</span>
            <strong>
              {kpi.unit === "CNY"
                ? money(kpi.value)
                : integer(kpi.value)}
            </strong>
            <small>{kpi.unit === "events" ? "去重业务事件" : kpi.unit}</small>
          </article>
        ))}
      </div>
      <div className="content-grid wide-left">
        <Panel title="支付与结算趋势" meta={`${data.trend.length} 个有效日期`}>
          <Chart option={trendOption} ariaLabel="支付金额与结算金额趋势图" />
        </Panel>
        <Panel title="数据解释边界" meta="Evidence first">
          <div className="note-stack">
            <div className="note-row">
              <span className="note-index">01</span>
              <p>缺失日期不补零，不同平台口径保留来源边界。</p>
            </div>
            <div className="note-row">
              <span className="note-index">02</span>
              <p>自动归因仅为候选推断；人工确认前不会进入真实案例库。</p>
            </div>
            <div className="note-row warning">
              <AlertTriangle size={17} />
              <p>商品到 WMS 库存、日报到结算流水仍缺可靠实体桥接。</p>
            </div>
          </div>
        </Panel>
      </div>
      <Panel title="店铺经营覆盖" meta={`更新至 ${data.data_updated_at ?? "—"}`}>
        <div className="shop-strip">
          {data.shops.map((shop) => (
            <div className="shop-chip" key={String(shop.shop_id)}>
              <span>{String(shop.shop_id)}</span>
              <strong>{money(shop.paid_amount)}</strong>
              <small>
                {integer(shop.paid_orders)} 单 · {String(shop.latest_date)}
              </small>
            </div>
          ))}
        </div>
      </Panel>
    </>
  );
}
