import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import type { EChartsOption } from "echarts";
import { ArrowLeft, CheckCircle2, ShieldCheck } from "lucide-react";
import { useMemo, useState } from "react";
import { api } from "../api";
import { Chart } from "../components/Chart";
import { DataTable } from "../components/DataTable";
import { PageHeader, Panel, StatusBadge } from "../components/Page";
import { ErrorState, LoadingState } from "../components/States";
import { asNumber, compactId, percent } from "../format";
import { Link } from "../router";

export function AnomalyDetailPage({ attributionId }: { attributionId: string }) {
  const queryClient = useQueryClient();
  const query = useQuery({
    queryKey: ["anomaly", attributionId],
    queryFn: () => api.anomaly(attributionId),
    enabled: Boolean(attributionId),
  });
  const [decision, setDecision] = useState<"accepted" | "rejected" | "corrected">("accepted");
  const [correctedCause, setCorrectedCause] = useState("");
  const [notes, setNotes] = useState("");
  const mutation = useMutation({
    mutationFn: () =>
      api.feedback(attributionId, {
        decision,
        corrected_cause_code: decision === "corrected" ? correctedCause : undefined,
        notes: notes || undefined,
        reviewer_alias: "Reviewer_Portfolio",
      }),
    onSuccess: () => {
      setNotes("");
      queryClient.invalidateQueries({ queryKey: ["anomaly", attributionId] });
    },
  });
  const option = useMemo<EChartsOption>(() => {
    const trend = query.data?.trend ?? [];
    const eventDate = String(query.data?.event.date ?? "");
    return {
      tooltip: { trigger: "axis" },
      legend: { top: 0, right: 0 },
      grid: { left: 54, right: 28, top: 44, bottom: 38 },
      xAxis: {
        type: "category",
        data: trend.map((row) => String(row.date).slice(5)),
        axisLabel: { color: "#777b77" },
      },
      yAxis: { type: "value", splitLine: { lineStyle: { color: "#e8e7e1" } } },
      series: [
        {
          name: "支付金额",
          type: "line",
          showSymbol: false,
          data: trend.map((row) => asNumber(row.paid_amount)),
          lineStyle: { color: "#173b39", width: 2.2 },
          markLine: eventDate
            ? {
                symbol: "none",
                label: { formatter: "异常日", color: "#d7522a" },
                lineStyle: { color: "#d7522a", type: "dashed" },
                data: [{ xAxis: eventDate.slice(5) }],
              }
            : undefined,
        },
        {
          name: "曝光人数",
          type: "line",
          showSymbol: false,
          data: trend.map((row) => asNumber(row.exposure_users)),
          lineStyle: { color: "#d76b32", width: 1.4 },
        },
      ],
    };
  }, [query.data]);
  if (query.isLoading) return <LoadingState label="正在装配异常证据包" />;
  if (query.error) return <ErrorState error={query.error} retry={() => query.refetch()} />;
  const data = query.data!;
  return (
    <>
      <Link className="back-link" to="/anomalies">
        <ArrowLeft size={15} /> 返回异常中心
      </Link>
      <PageHeader
        eyebrow={`Attribution / ${String(data.event.rule_id)}`}
        title={`${String(data.event.target_metric)} 异常详情`}
        description={`${compactId(data.event.entity_id)} · ${String(data.event.date)} · 所有结论均保留证据引用`}
        actions={<StatusBadge value={data.event.evidence_status} />}
      />
      <div className="content-grid wide-left">
        <Panel title="指标上下文" meta="异常日前14天至后7天">
          <Chart option={option} ariaLabel="异常指标相关趋势" />
        </Panel>
        <Panel title="报告校验" meta="Claim guard">
          <div className="validation-card">
            <ShieldCheck size={28} />
            <strong>
              {data.validation?.valid === false ? "报告未通过" : "引用约束已通过"}
            </strong>
            <p>事实必须引用当前 evidence_id；候选原因不能使用确定性因果措辞。</p>
            <div className="validation-metric">
              <span>Unsupported claims</span>
              <b>{String(data.validation?.unsupported_claim_count ?? 0)}</b>
            </div>
          </div>
        </Panel>
      </div>
      <Panel title="证据报告" meta={data.report ? "deterministic evidence template" : "尚未生成"}>
        {data.report ? (
          <div className="report-layout">
            <div className="report-summary">
              <span>SUMMARY</span>
              <p>{data.report.summary}</p>
            </div>
            <div>
              <h3>已确认事实</h3>
              <ul className="evidence-list">
                {data.report.confirmed_facts?.map((fact) => (
                  <li key={fact.evidence_ids.join("-")}>
                    <CheckCircle2 size={16} />
                    <span>{fact.fact}</span>
                    <code>{fact.evidence_ids[0]}</code>
                  </li>
                ))}
              </ul>
            </div>
            <div>
              <h3>候选解释</h3>
              {data.report.possible_causes?.map((cause) => (
                <div className="cause-row" key={`${cause.cause}-${cause.status}`}>
                  <StatusBadge value={cause.status} />
                  <p>{cause.cause}</p>
                  <strong>证据评分：{cause.evidence_score.toFixed(2)}</strong>
                </div>
              ))}
            </div>
          </div>
        ) : (
          <div className="empty-state">尚未运行 Phase 6 报告生成命令</div>
        )}
      </Panel>
      <div className="content-grid">
        <Panel title="规则候选" meta={`${data.candidates.length} 条`}>
          <DataTable
            rows={data.candidates}
            columns={[
              { key: "rule_id", label: "规则" },
              { key: "cause", label: "候选解释" },
              { key: "evidence_status", label: "状态", render: (value) => <StatusBadge value={value} /> },
              { key: "evidence_score", label: "证据评分", align: "right", render: percent },
            ]}
          />
        </Panel>
        <Panel title="人工确认" meta={`${data.feedback.length} 条反馈`}>
          <form
            className="feedback-form"
            onSubmit={(event) => {
              event.preventDefault();
              mutation.mutate();
            }}
          >
            <label>
              审核结论
              <select value={decision} onChange={(event) => setDecision(event.target.value as typeof decision)}>
                <option value="accepted">接受候选</option>
                <option value="rejected">拒绝候选</option>
                <option value="corrected">修正原因</option>
              </select>
            </label>
            {decision === "corrected" && (
              <label>
                修正原因代码
                <input
                  required
                  value={correctedCause}
                  onChange={(event) => setCorrectedCause(event.target.value)}
                  placeholder="例如 campaign_calendar"
                />
              </label>
            )}
            <label>
              复核说明
              <textarea
                value={notes}
                onChange={(event) => setNotes(event.target.value)}
                placeholder="不要填写姓名、电话、地址或账号凭证"
                rows={3}
              />
            </label>
            <button className="button-primary" type="submit" disabled={mutation.isPending}>
              {mutation.isPending ? "正在保存…" : "提交审核"}
            </button>
            {mutation.isError && <p className="form-error">{mutation.error.message}</p>}
            {mutation.isSuccess && <p className="form-success">反馈已写入独立审核库</p>}
          </form>
        </Panel>
      </div>
    </>
  );
}
