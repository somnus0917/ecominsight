import { useQuery } from "@tanstack/react-query";
import { ExternalLink } from "lucide-react";
import { api } from "../api";
import { DataTable } from "../components/DataTable";
import { PageHeader, Panel, StatusBadge } from "../components/Page";
import { ErrorState, LoadingState } from "../components/States";
import { compactId, percent } from "../format";
import { Link } from "../router";

export function AnomaliesPage() {
  const query = useQuery({ queryKey: ["anomalies"], queryFn: () => api.anomalies() });
  if (query.isLoading) return <LoadingState />;
  if (query.error) return <ErrorState error={query.error} retry={() => query.refetch()} />;
  const data = query.data!;
  return (
    <>
      <PageHeader
        eyebrow="Anomaly Center / 异常中心"
        title="异常事件与证据状态"
        description="同一对象、日期和指标的多个 detector 信号已合并；列表展示最高置信候选。"
      />
      <div className="summary-bar">
        <div>
          <span>事件总数</span>
          <strong>{data.total}</strong>
        </div>
        <div>
          <span>当前页</span>
          <strong>{data.items.length}</strong>
        </div>
        <div>
          <span>审核原则</span>
          <strong>Evidence → Inference</strong>
        </div>
      </div>
      <Panel title="异常事件" meta="点击进入证据链">
        <DataTable
          rows={data.items}
          rowKey={(row) => String(row.attribution_id)}
          columns={[
            { key: "date", label: "日期" },
            { key: "entity_id", label: "对象", render: compactId },
            { key: "target_metric", label: "指标" },
            { key: "severity", label: "严重程度", render: (value) => <StatusBadge value={value} /> },
            { key: "cause", label: "候选解释" },
            {
              key: "evidence_status",
              label: "证据状态",
              render: (value) => <StatusBadge value={value} />,
            },
            { key: "confidence", label: "置信度", align: "right", render: percent },
            {
              key: "attribution_id",
              label: "",
              align: "right",
              render: (value) => (
                <Link className="table-link" to={`/anomalies/${String(value)}`}>
                  详情 <ExternalLink size={13} />
                </Link>
              ),
            },
          ]}
        />
      </Panel>
    </>
  );
}
