# EcomInsight

Multi-platform E-commerce Analytics, Anomaly Detection and Evidence-based Attribution System.

EcomInsight is a portfolio-grade analytics project built from real multi-source e-commerce
operations data. The system treats the language model as a report writer over verified evidence,
not as a calculator or a source of causal claims.

## Current status

- Phase 0 complete: read-only data audit, data dictionary and architecture.
- Phase 1 complete: Python 3.12/uv project, configuration, logging and quality tooling.
- Phase 2 complete: privacy-first adapters, Parquet staging and DuckDB warehouse.
- Phase 3 complete: validated metric registry and shop, product, channel, search, inventory and
  financial marts.
- Phase 4 baseline complete: fixed threshold, Rolling Z-score, Rolling MAD and Isolation Forest,
  with real-warehouse alerts and controlled-label evaluation.
- Phase 5 complete: log-change metric decomposition, ten deterministic evidence rules,
  real-warehouse attribution tables and controlled-scenario evaluation.
- Phase 6 complete: local knowledge embeddings, parameterized SQL evidence tools,
  evidence-constrained JSON reports and retrieval/report evaluation.
- Phase 7 complete: FastAPI query service, separate human-feedback store, React/TypeScript
  operations console, responsive anomaly detail workflow and Docker Compose deployment.
- A fully synthetic, cross-domain 140-day demo dataset provides ten controlled anomaly scenarios
  for later detection and attribution evaluation.

## Product preview

![EcomInsight operations overview](docs/assets/ui/overview.png)

The anomaly detail page keeps metric context, confirmed facts, candidate inferences, source IDs and
human review in one auditable workflow:

![Evidence-based anomaly detail](docs/assets/ui/anomaly-detail.png)

## Verified local data

- 165 shop-day operation rows: 105 Douyin and 60 external-platform rows.
- 23 channel shop-days, 186 product-days and 362 search/source rows.
- 11 independent inventory snapshots.
- 612 authoritative order rows containing direct personal information.
- 6198 settlement business lines after excluding four file-summary rows.

These counts come from the Phase 0 read-only audit and are not synthetic performance claims.

## Architecture

```text
read-only sources
→ allowlist/denylist discovery
→ streaming privacy sanitizer
→ unit-aware Parquet staging
→ data contracts
→ DuckDB curated facts and dimensions
→ metrics
→ anomaly detection
→ evidence rules
→ constrained LLM report
```

See:

- [Data audit](docs/data_audit.md)
- [Data dictionary](docs/data_dictionary.md)
- [Architecture](docs/architecture.md)
- [Warehouse implementation](docs/warehouse.md)
- [Privacy and security](docs/privacy_and_security.md)
- [Metric definitions](docs/metric_definitions.md)
- [Phase 3 analysis](docs/phase3_analysis.md)
- [Phase 4 experiments](docs/experiments.md)
- [Phase 5 attribution experiments](docs/attribution_experiments.md)
- [Phase 6 retrieval and reporting experiments](docs/retrieval_reporting_experiments.md)
- [Synthetic data design](docs/synthetic_data.md)

## Privacy defaults

- Browser sessions, auth tables, config, logs and login screenshots are hard-excluded.
- Names, phones and addresses are removed before an order record can enter a DataFrame.
- Order, shop, product, SKU, creator, merchant and warehouse identifiers are stable HMAC aliases.
- The local HMAC salt is stored with mode `0600` outside version control.
- Real database, CSV, JSON, Parquet and DuckDB files are ignored.
- External APIs are disabled by default.

## 本地完整运行步骤

### 运行前准备

需要安装：Python 3.12、[uv](https://docs.astral.sh/uv/)、Node.js 22+ 与 npm。Docker 仅用于
容器化预览，不是本地开发的必需依赖。

进入项目根目录，并确认只读业务快照存在：

```bash
cd /Users/somnus/proj/EcomInsight
ls luopan-server-snapshot-20260727/current/state/luopan.db
```

安装 Python 依赖并创建本地配置：

```bash
uv sync --all-groups
cp .env.example .env
```

打开 `.env`，确认以下路径与当前目录结构一致；不要填写 Cookie、Token、账号或密钥：

```dotenv
ECOM_SOURCE_ROOT=./luopan-server-snapshot-20260727/current
ECOM_OUTPUT_ROOT=data/processed
ECOM_EXTERNAL_API_ENABLED=false
ECOM_API_DATABASE_PATH=data/processed/ecom_insight.duckdb
ECOM_API_FEEDBACK_DATABASE_PATH=data/processed/feedback.sqlite
```

### 首次构建分析仓库

按顺序运行以下命令。它们只读取 `luopan-server-snapshot-20260727`，不会修改原始数据库
或原始文件；中间结果与 DuckDB 分析仓库写入被 Git 忽略的 `data/processed/`。

```bash
uv run ecom-audit-data
uv run ecom-build-warehouse
uv run ecom-run-analysis
uv run ecom-run-anomaly
uv run ecom-run-attribution
uv run ecom-build-knowledge
uv run ecom-generate-reports
```

构建成功后应存在：

```bash
ls data/processed/ecom_insight.duckdb
```

可选：运行受控场景评测。评测结果用于算法回归，不代表真实业务准确率。

```bash
uv run ecom-evaluate-anomaly
uv run ecom-evaluate-attribution
uv run ecom-evaluate-reporting
```

### 启动 API 与前端预览

打开两个终端，第一个终端启动后端：

```bash
cd /Users/somnus/proj/EcomInsight
uv run ecom-api
```

可通过以下地址确认服务正常：

```bash
curl http://127.0.0.1:8000/api/health
```

第二个终端安装并启动前端：

```bash
cd /Users/somnus/proj/EcomInsight
npm --prefix frontend ci
npm --prefix frontend run dev
```

浏览器访问：

- 经营控制台：`http://127.0.0.1:5173`
- API 文档：`http://127.0.0.1:8000/docs`

前端会把 `/api` 自动代理到本地 FastAPI。默认不向外部模型或 API 发送公司数据。

### 运行质量检查

```bash
uv run pytest
uv run ruff check src tests scripts
uv run mypy src
npm --prefix frontend run check
npm --prefix frontend run build
npm --prefix frontend audit --audit-level=moderate
```

也可以使用 Makefile：

```bash
make check
make frontend-check
make frontend-build
```

### Docker 容器预览

先完成“首次构建分析仓库”，确保本地已有
`data/processed/ecom_insight.duckdb`，然后运行：

```bash
docker compose up --build
```

访问 `http://127.0.0.1:5173`，停止服务：

```bash
docker compose down
```

Compose 会只读挂载分析仓库，人工审核反馈写入独立 Docker volume。当前 Docker 配置已经过
`docker compose config` 校验；若本机无法拉取基础镜像，请先检查 Docker Desktop 与镜像仓库网络。

### 公开演示数据

不使用真实快照时，可以生成公开的合成数据：

```bash
uv run ecom-generate-demo-data
```

输出位于 `data/demo/generated/`。当前前端默认读取上述真实流程构建的 DuckDB；演示数据到
独立 DuckDB 的一键构建尚未封装。

详细的页面、接口与部署边界见 [Phase 7 应用与部署文档](docs/phase7_application.md)。

## Verified Phase 2 build

The warehouse was rebuilt twice against the audited snapshot with identical core row counts:

| Curated object | Rows |
|---|---:|
| `fact_shop_daily` | 165 |
| `fact_product_daily` | 186 |
| `fact_order_sanitized` | 612 |
| `fact_settlement` | 6198 |
| `fact_inventory_snapshot` | 12693 across 11 snapshots |
| `bridge_product_sku` | 7 candidate links |

The final quality report contains no failed checks. Its warning records 239 negative available
inventory observations across all historical snapshots; the latest snapshot contains the 28
already documented in Phase 0. Negative availability is retained rather than silently changed.

Curated money columns are `DECIMAL(18,2)` yuan. No raw receiver, phone, address, order-number,
credential or authentication columns exist in the generated warehouse.

## Synthetic evaluation data

The source snapshot is never padded with invented records. Insufficient history and unavailable
cross-domain links are handled through a separate `synthetic=true` dataset under
`data/demo/generated`. It reconciles shop, product, channel, search, inventory and financial
facts and carries controlled ground-truth labels.

The current demo contains 12,450 records and ten verified scenarios: traffic decline, click-rate
decline, conversion decline, average-order-value decline, refund spike, overstock, inefficient ad
spend, core-SKU stockout, commission spike and settlement decline. Synthetic and real evaluation
results must be reported separately.

## Known limitations

- Per-shop history is uneven: the four Douyin shops have 11, 39, 43 and 12 observations.
- Channel, product and search data cover only seven captured dates.
- Product IDs do not directly link platform product facts to WMS or settlement products.
- Current order and settlement extracts have no overlapping order identifiers.
- Activity calendars, price changes and ad-plan changes are not currently available, so
  correlations cannot be described as confirmed causes.
