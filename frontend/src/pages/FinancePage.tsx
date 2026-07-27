import { useQuery } from "@tanstack/react-query";
import type { EChartsOption } from "echarts";
import { api } from "../api";
import { Chart } from "../components/Chart";
import { DataTable } from "../components/DataTable";
import { PageHeader, Panel } from "../components/Page";
import { ErrorState, LoadingState } from "../components/States";
import { asNumber, integer, money } from "../format";

export function FinancePage() {
  const query = useQuery({ queryKey: ["finance"], queryFn: api.finance });
  if (query.isLoading) return <LoadingState />;
  if (query.error) return <ErrorState error={query.error} retry={() => query.refetch()} />;
  const rows = query.data ?? [];
  const option: EChartsOption = {
    tooltip: { trigger: "axis" },
    legend: { top: 0, right: 0 },
    grid: { left: 54, right: 30, top: 46, bottom: 38 },
    xAxis: {
      type: "category",
      data: rows.map((row) => String(row.settlement_date).slice(5)),
    },
    yAxis: { type: "value", splitLine: { lineStyle: { color: "#e8e7e1" } } },
    series: [
      {
        name: "用户实付",
        type: "line",
        showSymbol: false,
        data: rows.map((row) => asNumber(row.user_paid)),
        lineStyle: { color: "#173b39", width: 2 },
      },
      {
        name: "结算金额",
        type: "line",
        showSymbol: false,
        data: rows.map((row) => asNumber(row.settlement_amount)),
        lineStyle: { color: "#d76b32", width: 2 },
      },
      {
        name: "支出合计",
        type: "bar",
        data: rows.map((row) => asNumber(row.expense_total)),
        itemStyle: { color: "#aab1a8" },
      },
    ],
  };
  return (
    <>
      <PageHeader
        eyebrow="Settlement / 财务结算"
        title="结算日收入与费用"
        description="按结算日期展示流水汇总，不与支付日期日报强行对账。费用保留来源符号。"
      />
      <Panel title="实付、结算与支出趋势" meta={`${rows.length} 个结算日`}>
        <Chart option={option} ariaLabel="财务结算趋势图" />
      </Panel>
      <Panel title="财务日明细" meta="结算日期口径">
        <DataTable
          rows={rows}
          rowKey={(row) => String(row.settlement_date)}
          columns={[
            { key: "settlement_date", label: "结算日期" },
            { key: "orders", label: "订单", align: "right", render: integer },
            { key: "user_paid", label: "用户实付", align: "right", render: money },
            { key: "income_total", label: "收入合计", align: "right", render: money },
            { key: "settlement_amount", label: "结算金额", align: "right", render: money },
            { key: "subsidy_total", label: "补贴", align: "right", render: money },
            {
              key: "platform_service_fee",
              label: "平台服务费",
              align: "right",
              render: money,
            },
            {
              key: "creator_commission",
              label: "达人佣金",
              align: "right",
              render: money,
            },
            { key: "expense_total", label: "支出合计", align: "right", render: money },
          ]}
        />
      </Panel>
    </>
  );
}
