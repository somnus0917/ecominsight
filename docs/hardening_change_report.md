# 数据血缘与异常检测加固报告

本轮将 Demo 运行器的 `data_origin` 显式设为 `demo`，并把该来源写入异常、异常事件、归因、归因证据、报告及知识文档表；真实运行默认写入 `real`。

API 默认模式改为 `real`，启动时校验事实表的 `synthetic` 和下游 `data_origin`，不允许以 Demo 模式展示真实库，反之亦然。健康接口返回已通过的来源校验状态。

报告层将公开输出的 `confidence` 改为 `evidence_score`，旧 JSON 输入仍可读取；前端显示证据评分，不将其表述为概率。异常配置现在按指标选择检测器与阈值，固定阈值可区分相对变化、百分点变化和绝对阈值。检测器记录保留在 `fact_anomaly`，聚合后的事件写入 `fact_anomaly_event`，支持 any、consensus、weighted 策略并预留事件状态字段。

已验证：`uv run ecom-demo`、pytest、ruff、mypy、前端类型检查和生产构建。恢复状态的跨日期生命周期规则仍只保留表字段和状态接口，尚未完成完整状态机与专门回归评测。
