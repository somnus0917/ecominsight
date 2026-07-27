# Phase 6 本地检索与证据报告实验

## 技术结论

Phase 6 已建立“SQL 取事实、本地检索取案例、受约束生成器组织报告”的完整离线链路。
真实仓库运行生成 277 份异常报告和 1,896 条声明，277 份全部通过证据引用校验，
Unsupported Claim Count 为 0。

知识索引包含 52 篇文档：

| 文档类型 | 数量 | 数据来源 |
|---|---:|---|
| 指标定义 | 32 | `configs/metrics.yaml` |
| 归因规则 | 10 | `configs/attribution_rules.yaml` |
| 历史案例 | 10 | 公开受控场景 |
| 已审核真实案例 | 0 | 当前尚无人工确认记录 |

结构化金额和店铺日报不进入向量索引。自动生成的 308 个真实归因候选也不会在未经人工
确认时成为历史知识。方向一致性修复后的真实候选数为 306。

## 本地 Embedding 与检索

默认 Embedding Provider 使用 512 维中文字符 2～4 gram Hashing Vectorizer：

- 完全本地运行；
- 不需要拟合或训练；
- 相同文本和配置产生稳定向量；
- 不下载模型，不调用外部 API；
- 可通过 `EmbeddingProvider` 接口替换为 BGE、FAISS 或 Qdrant 实现。

向量和元数据写入同一个分析 DuckDB：

```text
dim_knowledge_document
fact_knowledge_embedding
```

这样不会引入第二个需要跨设备同步的业务数据仓。结构化指标继续通过参数化 SQL 查询，
只有指标定义、规则、已审核案例和脱敏报告适合进入检索层。

### 检索回归结果

10 个受控查询只包含异常指标、方向和预期证据名称，不包含 `scenario_type`、`cause_code`
或预期规则 ID。

| 指标 | 结果 |
|---|---:|
| Rule Hit@1 | 1.000 |
| Rule Hit@3 | 1.000 |
| Case Self-retrieval Hit@1 | 1.000 |
| Case Self-retrieval Hit@3 | 1.000 |

Case Self-retrieval 只验证索引构建、中文查询和元数据读取没有回归，不衡量未知案例泛化。
当前每个 `cause_code` 只有一个历史案例，留一后不存在同标签正例，因此案例泛化评测状态
明确记录为 `insufficient_data`。

## SQL 证据工具

`AttributionEvidenceService` 不接受任意 SQL，只暴露：

```text
list_attribution_ids(limit)
get_bundle(attribution_id)
```

`attribution_id` 必须满足 24 位十六进制格式，所有查询使用参数绑定。证据包只包含：

- 脱敏实体和日期；
- detector 集合与异常分数；
- 已验证 EvidenceItem；
- 规则候选、反向证据和缺失信息；
- 指标变化分解；
- 本次检索命中的知识文档。

该服务不会读取原始订单、姓名、电话、地址、Cookie、Token 或认证配置。

## 报告生成与幻觉约束

默认 `DeterministicEvidenceReportGenerator` 不使用大模型。可选
`StructuredLLMReportGenerator` 只依赖 provider-neutral 的 `StructuredLLMClient`
协议，调用方必须显式启用模型。

报告 JSON 包含：

```text
summary
summary_evidence_ids
confirmed_facts
possible_causes
missing_information
recommended_checks
retrieved_documents
generator
```

`ReportValidator` 在落库前执行：

1. 每个事实和候选原因引用的 `evidence_id` 必须存在于当前证据包；
2. 历史文档引用必须存在于当前检索结果；
3. `supported_inference` 不能没有支持证据；
4. “唯一原因”“确定导致”“已经证明”等确定性因果措辞会导致验证失败。

验证通过的报告写入 `fact_attribution_report`。真实运行结果：

| 指标 | 结果 |
|---|---:|
| 报告数 | 277 |
| 声明数 | 1,896 |
| 验证通过报告 | 277 |
| Unsupported Claim Count | 0 |
| 每份报告检索文档数 | 5 |

这表示引用完整性和确定性因果措辞约束通过，不表示所有归因候选都经过业务人员确认。
其中 159 个候选仍保持 `insufficient_data`。

## 架构变体对比

评测实际运行了三个离线变体。纯大模型基线因外部 API 默认关闭且未配置本地生成模型，
状态为 `not_run`，没有生成虚构数字。

| 变体 | 状态 | 报告/声明 | Unsupported Claim Rate | Evidence Coverage | 历史案例引用率 |
|---|---|---:|---:|---:|---:|
| Direct LLM | not_run | — | — | — | — |
| Rules only | completed | 10 / 10 | 1.000 | 0.000 | 0.000 |
| Rules + SQL | completed | 10 / 70 | 0.000 | 0.900 | 0.000 |
| Rules + SQL + RAG | completed | 10 / 70 | 0.000 | 0.900 | 0.600 |

`Rules only` 基线故意只输出原因标签而不附 `evidence_id`，用于验证证据引用约束的作用，
不能解释为规则引擎本身有 100% 幻觉率。

RAG 当前没有提升数值事实覆盖率，因为数值证据来自同一 SQL 工具；它提供的是可追溯的
规则、指标口径和历史案例上下文。Evidence Coverage 为 0.900 的原因是确定性模板最多
展示 5 条主要事实，30 个预期字段中有 3 个未进入最终引用集合，并非数据未检索。

## 当前不需要训练

Phase 6 没有需要训练的模型：

- Hashing Embedding 是无训练本地基线；
- 归因使用显式规则；
- 报告使用确定性证据模板；
- Isolation Forest 仅在历史窗口在线拟合，不产生需要保存的训练权重。

如果后续接入 BGE，仅需下载或配置预训练模型；如果要微调 Embedding 或大模型，则必须先
积累足量人工确认案例，并建立独立训练集、验证集和隐私审批流程。

## 限制与下一步

- 当前无可评测的真实人工确认归因标签；
- 每个原因只有一个历史案例，不能评测跨案例泛化；
- 字符 Hashing 是工程基线，不具备预训练中文语义模型的同义表达能力；
- Direct LLM 尚未运行，不能声称混合架构已经在同一模型上超过纯 LLM；
- 当前模板只展示 5 条主要事实，可能遗漏次要证据；
- 人工反馈表和案例晋升流程尚未接入 API。

Phase 7 应优先实现 FastAPI 的只读查询接口、人工确认/修正数据模型，以及总览和异常详情
页面。只有 `manual_confirmed` 的真实归因才能进入 `real_reviewed` 历史案例。

## 复现

```bash
uv run ecom-build-knowledge
uv run ecom-generate-reports
uv run ecom-evaluate-reporting
```

本地结果：

```text
dim_knowledge_document
fact_knowledge_embedding
fact_attribution_report
data/processed/artifacts/phase6_knowledge_summary.json
data/processed/artifacts/phase6_report_summary.json
data/processed/artifacts/reporting_evaluation.json
```
