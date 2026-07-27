import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { api } from "../api";
import { DataTable } from "../components/DataTable";
import { PageHeader, Panel, StatusBadge } from "../components/Page";
import { ErrorState, LoadingState } from "../components/States";
import { compactId, integer } from "../format";

export function InventoryPage() {
  const [status, setStatus] = useState("");
  const query = useQuery({
    queryKey: ["inventory", status],
    queryFn: () => api.inventory(status || undefined),
  });
  if (query.isLoading) return <LoadingState />;
  if (query.error) return <ErrorState error={query.error} retry={() => query.refetch()} />;
  return (
    <>
      <PageHeader
        eyebrow="Inventory / 库存健康"
        title="缺货风险与低动销"
        description="规则结果基于 WMS SKU 内部库存和动销；未确认的平台商品关联不会显示为销售损失原因。"
        actions={
          <select value={status} onChange={(event) => setStatus(event.target.value)} aria-label="库存状态">
            <option value="">全部状态</option>
            <option value="stockout_risk">缺货风险</option>
            <option value="out_of_stock">已缺货</option>
            <option value="overstock">高库存低动销</option>
            <option value="healthy">健康</option>
          </select>
        }
      />
      <Panel title="SKU 库存快照" meta={`${query.data?.length ?? 0} 条`}>
        <DataTable
          rows={query.data ?? []}
          rowKey={(row) => `${row.warehouse_id}-${row.sku_id}`}
          columns={[
            { key: "inventory_status", label: "状态", render: (value) => <StatusBadge value={value} /> },
            { key: "goods_name_masked", label: "商品" },
            { key: "sku_name_masked", label: "规格" },
            { key: "warehouse_name_masked", label: "仓库" },
            { key: "available_qty", label: "可用库存", align: "right", render: integer },
            { key: "locked_qty", label: "锁定", align: "right", render: integer },
            { key: "sales_7d", label: "近7日销量", align: "right", render: integer },
            { key: "days_of_supply", label: "可售天数", align: "right", render: integer },
            { key: "sku_id", label: "SKU ID", render: compactId },
          ]}
        />
      </Panel>
    </>
  );
}

