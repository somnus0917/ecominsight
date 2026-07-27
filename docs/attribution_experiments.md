# Phase 5 证据归因实验

## 技术结论

第一版归因引擎已把 296 条 detector-level 告警合并为 277 个“实体 × 日期 × 指标”
事件，生成 306 个候选归因和 2,797 条证据记录。候选中 159 条为
`insufficient_data`，置信度固定为 0；系统没有为了提高覆盖率而补写原因。

10 个公开演示受控场景的实际评测结果为：

| 指标 | 结果 |
|---|---:|
| Rule Top-1 Accuracy | 1.000 |
| Rule Candidate Recall | 1.000 |
| Evidence Precision | 0.750 |
| Evidence Coverage | 1.000 |
| Unsupported Claim Rate | 0.000 |
| Attribution Acceptance Rate | 1.000 |
| Hallucination Rate | 0.000 |

这些结果来自 `data/processed/artifacts/attribution_evaluation.json` 的本地实际运行。
受控场景是为验证规则覆盖和证据引用而设计的强信号测试，不能外推为真实生产准确率。

## 三层实现

### 指标变化分解

支付金额使用可审计的乘法分解：

```text
paid_amount ~= exposure_users
              * exposure_click_rate
              * click_conversion_rate
              * avg_order_value
```

所有值为正时计算 `delta log`，因子贡献之和与目标变化之间的差记为 residual。存在零值
或负值时切换为一阶相对变化近似，并在结果中保留方法、限制和残差；缺字段时返回
`insufficient_data`，不进行插值。

61 个真实支付金额异常事件中，36 个具备正值且字段完整，可使用对数分解。其余事件保留
不可分解原因，例如源字段缺失、零支付或零漏斗值。

### 证据规则

| 规则 | 候选原因 | 核心前置条件 | 主要支持证据 | 反向证据 |
|---|---|---|---|---|
| R001 | 流量下降 | 支付/曝光下降，曝光显著下降 | 曝光、自然搜索、搜索排名、稳定转化率 | 点击率或转化率同步大降 |
| R002 | 点击效率下降 | 曝光点击率下降 | 点击率、点击人数、支付、稳定曝光 | 曝光同步大降 |
| R003 | 成交转化下降 | 点击成交率下降 | 转化率、支付人数、支付、稳定点击率 | 点击率同步大降 |
| R004 | 客单价下降 | 客单价下降 | 客单价、件单价、支付、稳定转化率 | 转化率同步大降 |
| R005 | 退款压力上升 | 退款率上升至少 20% | 退款率、退款金额、净支付 | 当前无专用反向条件 |
| R006 | 投放效率下降 | 广告消耗上升且 ROAS 下降 | 消耗、ROAS、未同比增长的支付 | 当前无专用反向条件 |
| R007 | 主销规格库存不足 | 可用库存大降，商品支付或转化下降 | 库存、核心商品支付、转化 | 缺可靠桥接时不触发 |
| R008 | 平台佣金率上升 | 佣金率上升至少 20% | 佣金率、结算比例 | 当前无专用反向条件 |
| R009 | 结算侧调整变化 | 结算率或支付时间口径结算额下降 | 结算、支付稳定性、调整项 | 缺店铺—结算桥接时降置信度 |
| R010 | 高库存低动销 | 可售天数上升至少 50% | 可售天数、库存、近 7 日销量 | 当前无专用反向条件 |

规则输出始终是 `supported_inference`，支持证据本身是 `confirmed_fact`。规则 R000 专门
承接不满足前置条件的事件，状态为 `insufficient_data`。每个候选保存支持证据、反向
证据、缺失信息、解释模板和以下透明置信度分量：

```text
evidence_completeness
* source_reliability
* directional_consistency
* temporal_alignment
* (1 - contradiction_penalty)
```

### 证据落库

`fact_attribution` 以“异常事件 × 候选规则”为粒度，保存检测器集合、异常分数、证据等级、
置信度分解、解释和支付金额分解结果。`fact_attribution_evidence` 保存支持、反向和上下文
证据。

真实运行的证据来源为：

| 来源 | 证据记录 | 解释 |
|---|---:|---|
| `mart_shop_performance_daily` | 2,736 | 漏斗、支付、退款、投放和日报结算 |
| `fact_channel_daily` | 31 | 同店同日自然搜索上下文，标记部分覆盖 |
| `fact_product_daily` | 31 | 同店同日采集商品支付上下文，标记部分覆盖 |

商品和渠道上下文只有在规则方向条件满足时才成为支持证据，否则保留为 `context`。真实
库存不会通过商品名称强行关联，真实结算流水也不会通过无重合订单号强行关联。

## 真实结果分布

| 规则 | 候选数 | 平均置信度 | 解释 |
|---|---:|---:|---|
| R000 | 159 | 0.000 | 当前证据不足 |
| R001 | 30 | 0.543 | 流量下降候选 |
| R002 | 37 | 0.767 | 点击效率下降候选 |
| R003 | 41 | 0.710 | 成交转化下降候选 |
| R004 | 16 | 0.814 | 客单价下降候选 |
| R009 | 23 | 0.308 | 结算侧候选，因桥接缺失而降权 |

真实运行没有触发 R005、R006、R007、R008 和 R010。含义是当前异常事件与基线没有同时
满足这些规则的前置条件，或缺少可靠实体桥接；不能解释为业务中不存在退款、投放、库存
或佣金问题。

方向一致性回归测试要求：当目标事件是支付金额上升时，不允许把流量、点击、转化、
客单价、退款、投放或库存下降写成该事件的候选解释。该约束在真实流水线重跑后减少了
2 个方向不一致候选。

## 受控场景错误分析

全部 10 个场景的预期规则都排在第一位，但 Evidence Precision 为 0.750，而非 1.000。
原因是规则会引用预先声明证据集合之外、仍然与判定有关的辅助事实，例如流量场景中的
稳定点击率/转化率、结算场景中的稳定支付。评测按严格集合匹配将这些辅助事实计入分母。

Evidence Coverage 为 1.000，说明 30 个预先声明证据字段均被检索。Unsupported Claim
Rate 和 Hallucination Rate 为 0，是结构化实现的约束结果：候选不能创建不存在于
`EvidenceItem` 集合中的证据引用。这不表示规则推断已被证明为因果。

## 限制与下一步人工评审

- 真实数据没有完整归因标签，真实候选不能计算 Precision、Recall 或 Acceptance Rate。
- 受控场景信号较强，规则阈值与场景设计方向一致，Top-1 结果会高于弱信号生产环境。
- 当前证据基线使用最近 14 个有效观察的中位数，尚未区分活动日、节假日和恢复期。
- 真实渠道、商品数据仅覆盖 7 个采集日，跨维度证据无法覆盖大多数异常事件。
- 平台商品到 WMS SKU、店铺日报到结算流水的可靠桥接仍是最主要的归因数据缺口。

下一轮应建立真实事件人工评审表，记录事实正确性、证据引用、原因接受度、遗漏维度和
因果措辞，并分别统计已审核样本的 Evidence Precision、Unsupported Claim Rate 与
Attribution Acceptance Rate。

## 复现

```bash
uv run ecom-run-attribution
uv run ecom-evaluate-attribution
```

本地结果写入：

```text
fact_attribution
fact_attribution_evidence
data/processed/artifacts/phase5_attribution_summary.json
data/processed/artifacts/attribution_evaluation.json
data/processed/artifacts/attribution_predictions.json
```
