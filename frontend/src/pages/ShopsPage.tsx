import { useQuery } from "@tanstack/react-query";
import type { EChartsOption } from "echarts";
import { useState } from "react";
import { api } from "../api";
import { Chart } from "../components/Chart";
import { DataTable } from "../components/DataTable";
import { PageHeader, Panel } from "../components/Page";
import { ErrorState, LoadingState } from "../components/States";
import { asNumber, money, percent } from "../format";

export function ShopsPage() {
  const shops = useQuery({ queryKey: ["shops"], queryFn: api.shops });
  const [selected, setSelected] = useState<string>();
  const shopId = selected ?? String(shops.data?.[0]?.shop_id ?? "");
  const detail = useQuery({
    queryKey: ["shop", shopId],
    queryFn: () => api.shop(shopId),
    enabled: Boolean(shopId),
  });
  if (shops.isLoading || (shopId && detail.isLoading)) return <LoadingState />;
  if (shops.error) return <ErrorState error={shops.error} retry={() => shops.refetch()} />;
  if (detail.error) return <ErrorState error={detail.error} retry={() => detail.refetch()} />;
  const data = detail.data;
  const option: EChartsOption = {
    tooltip: { trigger: "axis" },
    legend: { top: 0, right: 0 },
    grid: { left: 52, right: 30, top: 44, bottom: 36 },
    xAxis: { type: "category", data: data?.trend.map((row) => String(row.date).slice(5)) },
    yAxis: [
      { type: "value", splitLine: { lineStyle: { color: "#e8e7e1" } } },
      { type: "value", min: 0, max: 1, axisLabel: { formatter: "{value}" } },
    ],
    series: [
      {
        name: "支付金额",
        type: "bar",
        data: data?.trend.map((row) => asNumber(row.paid_amount)),
        itemStyle: { color: "#173b39" },
      },
      {
        name: "点击率",
        type: "line",
        yAxisIndex: 1,
        data: data?.trend.map((row) => asNumber(row.exposure_click_rate)),
        itemStyle: { color: "#d76b32" },
      },
      {
        name: "转化率",
        type: "line",
        yAxisIndex: 1,
        data: data?.trend.map((row) => asNumber(row.click_conversion_rate)),
        itemStyle: { color: "#778c62" },
      },
    ],
  };
  return (
    <>
      <PageHeader
        eyebrow="Stores / 店铺诊断"
        title="店铺经营与漏斗"
        description="在同一店铺来源范围内查看支付、曝光、点击、转化和内容载体。"
        actions={
          <select value={shopId} onChange={(event) => setSelected(event.target.value)} aria-label="选择店铺">
            {shops.data?.map((shop) => (
              <option key={String(shop.shop_id)} value={String(shop.shop_id)}>
                {String(shop.shop_id)}
              </option>
            ))}
          </select>
        }
      />
      <Panel title="支付与漏斗效率" meta={shopId}>
        <Chart option={option} ariaLabel="店铺支付金额、点击率和转化率趋势图" />
      </Panel>
      <div className="content-grid">
        <Panel title="渠道构成" meta="采集覆盖范围内">
          <DataTable
            rows={data?.channels ?? []}
            columns={[
              { key: "channel_group", label: "渠道" },
              { key: "metric_value", label: "指标值", align: "right" },
              { key: "traffic_share", label: "平均占比", align: "right", render: percent },
            ]}
          />
        </Panel>
        <Panel title="内容载体贡献" meta="不可归一为全量">
          <DataTable
            rows={data?.carriers ?? []}
            columns={[
              { key: "content_type", label: "载体" },
              { key: "paid_amount", label: "支付金额", align: "right", render: money },
              {
                key: "exposure_conversion_rate_daily_mean",
                label: "曝光成交率",
                align: "right",
                render: percent,
              },
            ]}
          />
        </Panel>
      </div>
    </>
  );
}
