import { useQuery } from "@tanstack/react-query";
import { api } from "../api";
import { DataTable } from "../components/DataTable";
import { PageHeader, Panel, StatusBadge } from "../components/Page";
import { ErrorState, LoadingState } from "../components/States";
import { compactId, integer, money, percent } from "../format";

export function SearchPage() {
  const query = useQuery({ queryKey: ["search"], queryFn: () => api.search() });
  if (query.isLoading) return <LoadingState />;
  if (query.error) return <ErrorState error={query.error} retry={() => query.refetch()} />;
  return (
    <>
      <PageHeader
        eyebrow="Discovery / 搜索诊断"
        title="搜索词与行业区间"
        description="保留本店词和行业词的口径差异，排名和基准缺失不会被补造。"
      />
      <Panel title="搜索词表现" meta="按支付金额与最新排名排序">
        <DataTable
          rows={query.data ?? []}
          rowKey={(row) => `${row.shop_id}-${row.term_id}`}
          columns={[
            { key: "term_kind", label: "类型", render: (value) => <StatusBadge value={value} /> },
            { key: "term_id", label: "搜索词ID", render: compactId },
            { key: "shop_id", label: "店铺", render: compactId },
            { key: "latest_rank", label: "最新排名", align: "right", render: integer },
            { key: "best_rank", label: "最佳", align: "right", render: integer },
            { key: "worst_rank", label: "最差", align: "right", render: integer },
            { key: "paid_amount", label: "支付金额", align: "right", render: money },
            {
              key: "exposure_users_day_sum",
              label: "曝光人数日和",
              align: "right",
              render: integer,
            },
            {
              key: "exposure_change_rate_mean",
              label: "曝光变化均值",
              align: "right",
              render: percent,
            },
          ]}
        />
      </Panel>
    </>
  );
}

