import { useQuery } from "@tanstack/react-query";
import { api } from "../api";
import { DataTable } from "../components/DataTable";
import { PageHeader, Panel } from "../components/Page";
import { ErrorState, LoadingState } from "../components/States";
import { compactId, integer, money, percent } from "../format";

export function ProductsPage() {
  const query = useQuery({ queryKey: ["products"], queryFn: () => api.products() });
  if (query.isLoading) return <LoadingState />;
  if (query.error) return <ErrorState error={query.error} retry={() => query.refetch()} />;
  return (
    <>
      <PageHeader
        eyebrow="Products / 商品贡献"
        title="商品表现"
        description="商品列表是采集范围内的贡献视图，不代表完整店铺支付对账。"
      />
      <Panel title="商品支付与转化排行" meta={`${query.data?.length ?? 0} 个商品实体`}>
        <DataTable
          rows={query.data ?? []}
          rowKey={(row) => String(row.product_id)}
          columns={[
            { key: "paid_amount_rank", label: "排名", align: "right" },
            { key: "product_name_masked", label: "商品" },
            { key: "product_id", label: "商品ID", render: compactId },
            { key: "shop_id", label: "店铺", render: compactId },
            { key: "paid_amount", label: "支付金额", align: "right", render: money },
            { key: "paid_orders", label: "订单", align: "right", render: integer },
            { key: "click_rate", label: "点击率", align: "right", render: percent },
            {
              key: "click_conversion_rate",
              label: "点击成交率",
              align: "right",
              render: percent,
            },
            {
              key: "paid_amount_share_in_captured_products",
              label: "采集商品内贡献",
              align: "right",
              render: percent,
            },
          ]}
        />
      </Panel>
    </>
  );
}

