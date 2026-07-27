# EcomInsight 数据字典（Phase 0）

本字典记录实际字段、建议规范字段、单位、粒度和口径风险。所有规范金额在 curated 层统一为 `DECIMAL(18,2)` 元；staging 层保留原始单位和原始值，SQLite 金额字段以分存储。

## 1. 通用约定

| 项目 | 约定 |
|---|---|
| 日期 | `DATE`，Asia/Shanghai 业务日 |
| 时间 | `TIMESTAMP`，保留原始时区信息；源未提供时记录假设 |
| SQLite 金额 | `BIGINT` 分，规范化时除以 100 |
| 结算 CSV 金额 | `DECIMAL(18,2)` 元 |
| 比率 | 0～1 小数；展示层再格式化为百分比 |
| 变化率 | 小数，可小于 -1 的字段需校验；正向可大于 1 |
| 计数/库存 | 件或人/次，按字段定义，不做隐式换算 |
| 缺键 | `NULL + field_present=false`，不能默认补 0 |
| 实体名 | 内部分析层遮蔽；公开层合成 |
| 原始 ID | 仅在受控 staging；客户/订单 ID 使用 HMAC |

建议所有事实表附带：

```text
source_system
source_table
source_record_id
source_unit
captured_at
loaded_at
quality_flags
```

## 2. SQLite 顶层表

### `operation_records`

粒度：`shop_id × date`。

| 原字段 | 类型 | 规范字段/用途 | 备注 |
|---|---|---|---|
| `shop_id` | TEXT | `shop_id` | 主键组成；源内可靠 |
| `date` | TEXT | `date` | ISO 日期 |
| `shop_name` | TEXT | `shop_name_masked` | 原值不得进入公开层 |
| `captured_at` | TEXT | `captured_at` | 采集时间 |
| `metrics_json` | TEXT JSON | 展开到 `fact_shop_daily` | 字段集合不固定 |
| `content_json` | TEXT JSON | 展开到内容载体事实 | 金额，单位分 |
| `trend_json` | TEXT JSON | 暂不使用 | 105 行均为空对象 |
| `source` | TEXT | `source_system` | `daily_json` / `external_orders` |
| `source_key` | TEXT NULL | `external_source_key` | 抖音日报 105 行为空 |
| `source_label` | TEXT NULL | `external_source_label_masked` | 抖音日报 105 行为空 |
| `source_file` | TEXT | `source_file_id` | 外部平台 60 行为空字符串 |
| `updated_at` | TEXT | `source_updated_at` | 源更新时间 |

### 渠道三表

| 表 | 主键 | JSON 字段 | 规范目标 |
|---|---|---|---|
| `channel_daily` | `shop_id,date` | `traffic_json` | `fact_channel_daily`、`fact_content_carrier_daily` |
| `channel_product_daily` | `shop_id,date,product_id` | `payload_json` | `fact_product_daily` |
| `channel_search_daily` | `shop_id,date,kind,row_key` | `payload_json` | `fact_search_term_daily` / `fact_traffic_source_daily` |

三个表还包含 `updated_at`；`channel_daily` 另有 `shop_name`、`captured_at`。所有 JSON 均可解析。

### 硬排除表

| 表 | 字段 | 原因 |
|---|---|---|
| `sessions` | `token_hash, username, created_at, expires_at` | 认证数据 |
| `users` | `username, password_hash, role, created_at, password_changed_at` | 凭证数据 |
| `app_kv` | `key, value_json, updated_at` | 运行配置可能含敏感信息 |
| `order_import_batches` | `id, created_at, payload_json, updated_at` | 仅导入元数据；不作为事实源 |

`metrics.db.metrics` 有 `id,captured_at,url,body_preview,body,shop_id,shop_name,data_date,date_type,endpoint`，但行数为 0。

## 3. `fact_shop_daily`

权威来源：`operation_records.metrics_json`。外部平台只提供四个指标，必须保留 `source_system`，不可与抖音缺失字段混为 0。

| 源键 | 规范字段 | 业务定义 | 源单位 | 抖音覆盖 | 注意事项 |
|---|---|---|---|---:|---|
| `income_amt` | `gmv` | 成交金额 | 分 | 100% | 外部源与 `pay_amt` 同值，口径待确认 |
| `pay_amt` | `paid_amount` | 用户支付金额 | 分 | 100% | 核心销售指标 |
| `pay_cnt` | `paid_orders` | 成交订单数 | 单 | 100% | 外部源也有 |
| `pay_item_cnt` | `paid_items` | 成交件数 | 件 | 78.1% | 外部源也有 |
| `pay_ucnt` | `paid_users` | 成交人数 | 人 | 100% | 外部源缺失 |
| `per_usr_pay_amt` | `avg_order_value` | 客单价 | 分/人 | 72.4% | 可重算并与源值对账 |
| `per_item_pay_amt` | `avg_item_price` | 件单价 | 分/件 | 54.3% | 分母为成交件数 |
| `product_show_ucnt` | `exposure_users` | 商品曝光人数 | 人 | 100% | 人数口径 |
| `product_show_cnt` | `exposure_count` | 商品曝光次数 | 次 | 78.1% | 次数口径 |
| `product_click_ucnt` | `click_users` | 商品点击人数 | 人 | 100% | 人数口径 |
| `product_click_cnt` | `click_count` | 商品点击次数 | 次 | 78.1% | 次数口径 |
| `product_show_click_ucnt_ratio` | `exposure_click_rate_users` | 曝光到点击率 | 0～1 | 100% | 人数口径 |
| `product_click_pay_ucnt_ratio` | `click_conversion_rate_users` | 点击到成交率 | 0～1 | 100% | 人数口径 |
| `product_show_pay_ucnt_ratio` | `exposure_conversion_rate_users` | 曝光到成交率 | 0～1 | 78.1% | 人数口径 |
| `product_show_click_cnt_ratio` | `exposure_click_rate_count` | 曝光到点击率 | 0～1 | 78.1% | 次数口径，不与人数口径合并 |
| `product_click_pay_cnt_ratio` | `click_conversion_rate_count` | 点击到成交率 | 0～1 | 78.1% | 次数口径 |
| `product_show_pay_cnt_ratio` | `exposure_conversion_rate_count` | 曝光到成交率 | 0～1 | 78.1% | 次数口径 |
| `pay_amt_per_k_show` | `gpm` | 千次曝光用户支付金额 | 分 | 45.7% | 大量源缺失/零值 |
| `refund_amt_pay_time` | `refund_amount_by_pay_time` | 按支付时间统计退款金额 | 分 | 36.2% | 不等于退款日口径 |
| `refund_order_cnt_pay_time` | `refund_orders_by_pay_time` | 按支付时间统计退款订单 | 单 | 34.3% | 同上 |
| `refund_amt_rate` | `refund_rate_by_pay_time` | 退款金额率 | 0～1 | 98.1% | 需验证分母 |
| `deal_refund_amt_pay_time` | `deal_refund_amount_by_pay_time` | 成交退款金额 | 分 | 21.9% | 中文口径待业务确认 |
| `refund_amt` | `refund_amount_by_refund_time` | 按退款时间退款金额 | 分 | 21.9% | 仅后段数据 |
| `rfndsuc_amt` | `successful_refund_amount` | 退款成功金额 | 分 | 21.9% | 与 `refund_amt` 关系待确认 |
| `refund_order_cnt` | `refund_orders_by_refund_time` | 按退款时间退款订单 | 单 | 21.9% | 仅后段数据 |
| `settlement_amt_pay_time` | `settlement_amount_by_pay_time` | 结算金额 | 分 | 100% | 与流水结算不是同粒度 |
| `settlement_amt_7d` | `settlement_amount_7d` | 7 日结算金额 | 分 | 78.1% | 窗口指标 |
| `settlement_amt_14d` | `settlement_amount_14d` | 14 日结算金额 | 分 | 78.1% | 窗口指标 |
| `expense_amt` | `expense_amount` | 支出金额 | 分 | 70.5% | 组成项待核 |
| `ad_cost_amt` | `ad_spend` | 投放消耗（店铺被投） | 分 | 70.5% | 不等同广告支付金额 |
| `platform_subsidy_amt` | `platform_subsidy` | 平台补贴 | 分 | 94.3% | 财务口径 |
| `talent_subsidy_amt` | `creator_subsidy` | 达人补贴 | 分 | 74.3% | 财务口径 |
| `platform_commission_amt` | `platform_commission` | 平台佣金（已结算） | 分 | 94.3% | 与结算流水对账后再合并 |
| `talent_commission_amt` | `creator_commission` | 达人佣金（已结算） | 分 | 94.3% | 同上 |
| `service_score` | `merchant_experience_score` | 商家体验分 | 分值 | 100% | 实际范围 76～99 |

### 内容载体

`content_json` 的值为对应载体支付金额，单位分：

| 源键 | 规范载体 | 覆盖 | 备注 |
|---|---|---:|---|
| `live` | `live` | 100% | 直播 |
| `product_card` | `product_card` | 100% | 商品卡 |
| `video` | `short_video` | 81.9% | 短视频 |
| `artc_video` | `article_or_video` | 80.0% | 原名称缩写含义需确认 |
| `other_content` | `other` | 98.1% | 其他 |

建议展开为 `fact_content_daily(shop_id,date,content_type,paid_amount)`，而不是在主事实表不断加列。

## 4. `fact_product_daily`

来源：`channel_product_daily.payload_json`，粒度为店铺 × 日 × 商品。

| 源字段 | 规范字段 | 类型/单位 | 空值 | 备注 |
|---|---|---|---:|---|
| `product_id` | `product_id` | TEXT | 0 | 源内主键 |
| `product_name` | `product_name_masked` | TEXT | 0 | 商业敏感 |
| `product_image` | `product_image_ref` | TEXT | 0 | 外链可能泄露商品信息 |
| `product_price` | `price` | 分 | 0 | 规范化为元 |
| `pay_amt` | `paid_amount` | 分 | 0 | |
| `pay_cnt` | `paid_orders` | 单 | 25 | |
| `pay_ucnt` | `paid_users` | 人 | 0 | |
| `show_ucnt` | `exposure_users` | 人 | 0 | |
| `click_ucnt` | `click_users` | 人 | 25 | |
| `click_rate` | `click_rate` | 0～1 | 25 | |
| `click_pay_rate` | `click_conversion_rate` | 0～1 | 25 | |
| `pay_amt_change` | `paid_amount_change_rate` | 变化率 | 22 | 可大于 1 或等于 -1 |
| `show_ucnt_change` | `exposure_change_rate` | 变化率 | 2 | |
| `first_onshelf_date` | `first_listed_at` | 日期/时间文本 | 25 | 需解析和时区校验 |

商品 ID 与库存 `goods_no/spec_no` 无精确重合，不能直接建外键。

## 5. 渠道与载体事实

`channel_daily.traffic_json` 同时包含三种结构，建议拆成长表。

### `fact_channel_daily`

粒度：店铺 × 日 × 渠道来源。

| JSON 路径 | 规范字段 | 单位/含义 |
|---|---|---|
| `sources[].code` | `channel_code` | 来源代码 |
| `sources[].name` | `channel_name_masked` | 来源名 |
| `sources[].parent` | `parent_channel_code` | 19 行为空 |
| `sources[].group` | `channel_group` | 归组 |
| `sources[].value` | `exposure_users` | `source_metric` 指定的度量 |
| `sources[].source_ratio` | `traffic_share` | 0～1 |
| `source_metric` | `source_metric_code` | 18/23 店铺日出现 |
| `source_total` | `source_total` | 18/23 店铺日出现 |
| `groups.organic_search.value/ratio` | 自然搜索量/占比 | 18/23 店铺日 |
| `groups.recommendation.value/ratio` | 推荐量/占比 | 18/23 |
| `groups.paid.value/ratio` | 付费量/占比 | 18/23；当前值均为 0 |
| `groups.short_video.value/ratio` | 短视频量/占比 | 18/23 |

`available_channels[]` 含 `channel_type,group,name,sub_channel_code`，是可选渠道维度，不是每日表现事实。

### `fact_content_carrier_daily`

载体：`all, article, live, other, product_card, short_video, talent`。

可出现字段：

```text
pay_amt
refund_rate
show_pay_ucnt_rate
show_ucnt
show_ucnt_benchmark
show_ucnt_change
watch_ucnt
watch_ucnt_benchmark
watch_ucnt_change
gpm
gpm_benchmark
```

不同载体字段集合不同。例如 article/short_video 主要使用观看人数，product card/live 使用曝光人数。适配器必须按载体校验，不得把缺字段填 0。

## 6. 搜索和来源

### 公共主键

```text
shop_id
date
kind
row_key
```

### `industry_term`

| 字段 | 类型/单位 | 说明 |
|---|---|---|
| `word` | TEXT | 行业搜索词，商业敏感 |
| `rank` | INTEGER | 1～5 |
| `pay_amt_change` | 变化率 | 实际金额为空 |
| `show_ucnt_change` | 变化率 | 实际曝光为空 |
| `pay_amt_lower/upper` | 分 | 行业金额区间 |
| `show_ucnt_lower/upper` | 人 | 行业曝光区间 |

### `shop_term`

同样包含 `word,rank,pay_amt,show_ucnt,pay_amt_change,show_ucnt_change`，但四个行业上下限字段为空。

### `source`

| 字段 | 类型/单位 | 说明 |
|---|---|---|
| `name` | TEXT | 搜索/流量来源 |
| `pay_amt` | 分 | 支付金额 |
| `pay_amt_change` | 变化率 | 77/132 为空 |
| `pay_amt_benchmark` | 分 | 3/132 为空 |
| `show_ucnt` | 人 | 曝光人数 |
| `show_ucnt_change` | 变化率 | 26/132 为空 |
| `show_ucnt_benchmark` | 人 | 3/132 为空 |

建议将 `source` 行写入 `fact_traffic_source_daily`，不要和搜索词行混用一个宽表。

## 7. 库存

### `fact_inventory_snapshot`

粒度：快照日 × 仓库 × 规格。

| 原字段 | 规范字段 | 类型/单位 | 质量说明 |
|---|---|---|---|
| `warehouse_no` | `warehouse_id` | TEXT | 直接键 |
| `warehouse_name` | `warehouse_name_masked` | TEXT | 商业敏感 |
| `brand_no` | `brand_id` | TEXT | 内部编码 |
| `brand_name` | `brand_name_masked` | TEXT | 商业敏感 |
| `goods_no` | `goods_id` | TEXT | 不能直接关联平台商品 ID |
| `goods_name` | `goods_name_masked` | TEXT | 商业敏感 |
| `spec_no` | `sku_id` | TEXT | 可与部分订单商家编码候选关联 |
| `spec_name` | `sku_name_masked` | TEXT | 81 个空字符串 |
| `stock_num` | `stock_qty` | 件 | 0～1760 |
| `available_num` | `available_qty` | 件 | -17～1760；28 个负数 |
| `lock_num` | `locked_qty` | 件 | 当前全 0 |
| `today_num` | `today_qty` | 件 | 当前全 0，口径不明 |
| `last_inout_time` | `last_movement_at` | TIMESTAMP | 入/出库合并时间 |
| `modified` | `source_modified_at` | TIMESTAMP | WMS 更新时间 |

### `fact_inventory_flow_daily`

`sales_7d` 和 `inbound_30d` 结构一致：

```text
warehouse_no
spec_no
date
quantity
flow_type = sale | inbound
```

当前销量 104 行、入库 617 行，组合键无重复且都可关联回库存。

## 8. 脱敏订单

原始 17 列：

| 原字段 | 处理 | 规范字段 |
|---|---|---|
| `order_no` | 外部盐 HMAC | `order_anon_id` |
| `item_order_id` | 外部盐 HMAC | `suborder_anon_id` |
| `receiver_name` | 删除 | 不落库 |
| `receiver_phone` | 删除 | 不落库 |
| `receiver_address` | 删除；本项目当前不提取省份 | 不落库 |
| `order_time` | 解析 | `ordered_at` |
| `product_name` | 内部遮蔽；公开合成 | `product_name_masked` |
| `sku_spec` | 内部遮蔽；公开合成 | `sku_name_masked` |
| `merchant_sku_code` | 受控内部编码/HMAC | `merchant_sku_anon_id` |
| `author` | 遮蔽 | `creator_anon_id` |
| `header_extra` | 先验证含义 | `source_header_extra` |
| `product_tags` | 清洗后保留 | `product_tags` |
| `price_quantity` | 解析并校验 | `unit_price`,`quantity` |
| `aftersale_status` | 枚举规范化 | `aftersale_status` |
| `order_status` | 枚举规范化 | `order_status` |
| `merchant_income` | 解析为元 | `merchant_income` |
| `operations` | 默认丢弃 | 页面操作文本，不是业务事实 |

原始订单文件不得直接读入 Polars/Pandas 后再脱敏；必须由流式 sanitizer 先处理。

## 9. 外部平台店铺日

`orders_daily.json.records[]`：

| 字段 | 规范字段 | 说明 |
|---|---|---|
| `shop_id` | `shop_id` | 4 个不同店铺 |
| `shop_name` | `shop_name_masked` | 商业敏感 |
| `date` | `date` | |
| `metrics.income_amt` | `gmv` | 分；与 pay_amt 同值 |
| `metrics.pay_amt` | `paid_amount` | 分 |
| `metrics.pay_cnt` | `paid_orders` | 单 |
| `metrics.pay_item_cnt` | `paid_items` | 件 |
| `content` | 不展开 | 当前空对象 |
| `trend` | 不展开 | 当前空对象 |
| `source` | `source_system` | |
| `source_key` | `external_source_key` | 3 个来源 |
| `source_label` | `platform_label_masked` | 3 个来源标签 |
| `source_file` | `source_file_id` | 不保留真实路径 |

导入元数据还包含文件名、文件哈希、输入行、接受订单数、重复订单数和批次日期范围；可进入 lineage 表，不进入经营事实。

## 10. 结算流水

粒度：结算流水行。先排除订单号和子订单号同时为空的 4 条文件汇总行。

### 标识、时间和分类

| 原字段 | 规范字段/处理 |
|---|---|
| `结算时间` | `settled_at` |
| `订单号` | 外部盐 HMAC → `order_anon_id` |
| `子订单号` | 外部盐 HMAC → `suborder_anon_id` |
| `结算账户` | 遮蔽 → `settlement_account_anon_id` |
| `结算单类型` | `settlement_type` |
| `有结算前退款` | `has_pre_settlement_refund` |
| `下单时间` | `ordered_at` |
| `商品ID` | 源内 `product_id`；不能关联渠道商品 ID |
| `商品名称` | `product_name_masked` |
| `商品数量` | `quantity` |
| `达人ID` | 遮蔽 → `creator_anon_id` |
| `达人名称` | 删除或遮蔽 |
| `业务类型` | `business_type` |
| `订单类型` | `order_type` |
| `是否免佣` | `is_commission_waived` |
| `商户主体名称` | 遮蔽 → `merchant_entity_anon_id` |
| `APP渠道` | `app_channel`；当前全空 |
| `其他分成说明` | `other_share_description`；当前全空 |
| `备注` | 默认不入分析层，先做敏感扫描 |

### 金额字段

以下原字段均为元的小数，规范层使用 `DECIMAL(18,2)`：

```text
结算金额
订单总价
商品总价
运费
店铺券
政府补贴商家垫资
结算前退款金额
平台补贴
其他平台补贴
政府补贴平台垫资
达人补贴
抖音支付补贴
抖音月付营销补贴
银行补贴
以旧换新抵扣
平台补贴运费
用户实付
收入合计
平台服务费
达人佣金
服务商佣金
渠道分成
招商服务费
站外推广费
其他分成
支出合计
免佣金额
```

费用字段通常以负数表示扣减，但平台补贴、其他分成和调整项可能双向。规范层必须同时保留：

```text
source_amount
source_sign
normalized_effect_on_net_income
settlement_type
```

不能只做 `abs()`，也不能按“负数即异常”处理。

## 11. 维度和桥接表

| 表 | 关键字段 | 来源 |
|---|---|---|
| `dim_date` | 日期、周、月、工作日、已知活动标记 | 日历 + 后续人工活动表 |
| `dim_platform` | 平台匿名 ID、来源类型 | source/source_key |
| `dim_shop` | shop_id、匿名名、平台、有效期 | 各源店铺 |
| `dim_product` | source_product_id、匿名名、源系统 | 商品/订单/结算分别建源内实体 |
| `dim_sku` | source_sku_id、匿名规格 | WMS/订单 |
| `dim_channel` | code、parent、group | 渠道 JSON |
| `dim_content_type` | live/product_card/... | 内容 JSON |
| `dim_warehouse` | warehouse_id、匿名名 | 库存 |
| `bridge_entity_link` | left/right、method、status、confidence | 人工确认或规则候选 |
| `bridge_product_sku` | product、sku、method、valid_from/to | 不允许仅名称自动确认 |

## 12. 待确认字段

- `income_amt` 的“成交金额”在不同平台是否同口径；
- `pay_cnt` 在外部平台是否为订单数而非支付笔数；
- `deal_refund_amt_pay_time` 与 `refund_amt_pay_time` 的差别；
- `rfndsuc_amt` 与 `refund_amt` 的关系；
- `artc_video` 的确切中文定义；
- `source_metric` 的所有可能枚举及单位；
- `today_num` 和 WMS 锁定/占用的完整口径；
- 订单 `price_quantity` 的稳定格式；
- `merchant_sku_code = spec_no` 是否为官方编码关系；
- 结算各类型的符号方向和净收入公式。
