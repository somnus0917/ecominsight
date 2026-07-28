from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import duckdb
import structlog

from ecom_insight.attribution.config import AttributionRulesConfig
from ecom_insight.metrics import MetricRegistry
from ecom_insight.retrieval.embedding import (
    EmbeddingProvider,
    LocalHashingEmbeddingProvider,
)
from ecom_insight.retrieval.index import KnowledgeIndex
from ecom_insight.retrieval.models import KnowledgeDocument

LOGGER = structlog.get_logger(__name__)

SCENARIO_CAUSE_CODES = {
    "traffic_drop": "traffic_decline",
    "click_rate_drop": "click_efficiency_decline",
    "conversion_drop": "conversion_decline",
    "aov_drop": "aov_decline",
    "refund_spike": "refund_pressure",
    "ad_waste": "ad_inefficiency",
    "stockout": "inventory_shortage",
    "commission_spike": "commission_pressure",
    "settlement_drop": "settlement_adjustment_decline",
    "overstock": "overstock",
}


@dataclass(frozen=True, slots=True)
class KnowledgeBuildResult:
    database_path: Path
    artifact_path: Path
    document_count: int
    document_type_counts: dict[str, int]
    embedding_model: str


def _stable_id(prefix: str, value: str) -> str:
    digest = hashlib.sha256(value.encode("utf-8")).hexdigest()[:20]
    return f"{prefix}_{digest}"


def _load_record_list(path: Path) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, list) or not all(isinstance(item, dict) for item in payload):
        raise ValueError(f"Expected JSON record list: {path}")
    return payload


class KnowledgeBuilder:
    def __init__(
        self,
        *,
        database_path: Path,
        metric_config_path: Path,
        rule_config_path: Path,
        demo_root: Path,
        artifact_root: Path,
        embedding_provider: EmbeddingProvider | None = None,
    ) -> None:
        self.database_path = database_path.resolve()
        self.metric_config_path = metric_config_path.resolve()
        self.rule_config_path = rule_config_path.resolve()
        self.demo_root = demo_root.resolve()
        self.artifact_root = artifact_root.resolve()
        self.embedding_provider = embedding_provider or LocalHashingEmbeddingProvider()

    def run(self) -> KnowledgeBuildResult:
        if not self.database_path.is_file():
            raise FileNotFoundError(self.database_path)
        documents = [
            *self._metric_documents(),
            *self._rule_documents(),
            *self._case_documents(),
        ]
        index = KnowledgeIndex.build(documents, self.embedding_provider)
        with duckdb.connect(str(self.database_path)) as connection:
            self._publish(connection, index)
        type_counts: dict[str, int] = {}
        for document in documents:
            type_counts[document.document_type] = (
                type_counts.get(document.document_type, 0) + 1
            )
        payload = {
            "schema_version": "1",
            "document_count": len(documents),
            "document_type_counts": type_counts,
            "embedding_model": self.embedding_provider.model_name,
            "embedding_dimensions": self.embedding_provider.dimensions,
            "external_api_used": False,
            "real_reviewed_case_count": 0,
            "safety_notes": [
                "结构化经营指标不进入向量索引。",
                "当前历史案例全部来自公开受控场景。",
                "自动生成的真实归因候选未经人工确认, 不进入案例知识库.",
            ],
        }
        self.artifact_root.mkdir(parents=True, exist_ok=True)
        artifact_path = self.artifact_root / "phase6_knowledge_summary.json"
        artifact_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        LOGGER.info(
            "phase6_knowledge_complete",
            document_count=len(documents),
            document_type_counts=type_counts,
            embedding_model=self.embedding_provider.model_name,
        )
        return KnowledgeBuildResult(
            database_path=self.database_path,
            artifact_path=artifact_path,
            document_count=len(documents),
            document_type_counts=type_counts,
            embedding_model=self.embedding_provider.model_name,
        )

    def _metric_documents(self) -> list[KnowledgeDocument]:
        registry = MetricRegistry.load(self.metric_config_path)
        return [
            KnowledgeDocument(
                document_id=f"metric:{metric.code}",
                document_type="metric_definition",
                title=f"{metric.name} ({metric.code})",
                content=(
                    f"业务定义: {metric.definition}\n公式: {metric.formula}\n"
                    f"来源: {metric.source}\n粒度: {metric.grain}\n单位: {metric.unit}\n"
                    f"空值策略: {metric.null_policy}\n注意事项: {'; '.join(metric.caveats)}"
                ),
                origin="public",
                anomaly_metric=metric.code,
                source_ref="configs/metrics.yaml",
                tags=[metric.role, metric.unit, *metric.applicable_platforms],
            )
            for metric in registry.config.metrics
        ]

    def _rule_documents(self) -> list[KnowledgeDocument]:
        config = AttributionRulesConfig.load(self.rule_config_path)
        return [
            KnowledgeDocument(
                document_id=f"rule:{rule.rule_id}",
                document_type="attribution_rule",
                title=f"{rule.rule_id} {rule.cause}",
                content=(
                    f"适用指标: {', '.join(rule.applies_to)}\n"
                    f"前置条件: {'; '.join(rule.preconditions)}\n"
                    f"支持证据: {', '.join(rule.supporting_evidence)}\n"
                    f"反向证据: {', '.join(rule.counter_evidence) or '无专用条件'}\n"
                    f"解释模板: {rule.explanation_template}"
                ),
                origin="public",
                anomaly_metric=rule.applies_to[0],
                cause_code=rule.cause_code,
                source_ref="configs/attribution_rules.yaml",
                tags=[rule.rule_id, *rule.applies_to, *rule.supporting_evidence],
            )
            for rule in config.rules
        ]

    def _case_documents(self) -> list[KnowledgeDocument]:
        labels = _load_record_list(self.demo_root / "anomaly_labels.json")
        documents: list[KnowledgeDocument] = []
        for label in labels:
            scenario_type = str(label["scenario_type"])
            source_key = str(label["scenario_id"])
            documents.append(
                KnowledgeDocument(
                    document_id=_stable_id("case", source_key),
                    document_type="historical_case",
                    title=f"受控历史案例 {label['target_metric']}",
                    content=(
                        f"异常指标: {label['target_metric']}\n"
                        f"变化方向: {label['expected_direction']}\n"
                        f"已验证证据: {', '.join(str(item) for item in label['expected_evidence'])}\n"
                        f"人工原因标签: {scenario_type}"
                    ),
                    origin="demo",
                    shop_id=str(label["entity_id"]),
                    product_id=(
                        str(label["target_product_id"])
                        if label.get("target_product_id") is not None
                        else None
                    ),
                    start_date=str(label["start_date"]),
                    end_date=str(label["end_date"]),
                    anomaly_metric=str(label["target_metric"]),
                    cause_code=SCENARIO_CAUSE_CODES[scenario_type],
                    source_ref="data/demo/generated/anomaly_labels.json",
                    tags=[
                        scenario_type,
                        str(label["expected_direction"]),
                        *(str(item) for item in label["expected_evidence"]),
                    ],
                )
            )
        return documents

    @staticmethod
    def _publish(
        connection: duckdb.DuckDBPyConnection,
        index: KnowledgeIndex,
    ) -> None:
        connection.execute(
            """
            CREATE OR REPLACE TABLE dim_knowledge_document (
                document_id VARCHAR PRIMARY KEY,
                document_type VARCHAR NOT NULL,
                title VARCHAR NOT NULL,
                content VARCHAR NOT NULL,
                origin VARCHAR NOT NULL,
                shop_id VARCHAR,
                product_id VARCHAR,
                start_date VARCHAR,
                end_date VARCHAR,
                anomaly_metric VARCHAR,
                cause_code VARCHAR,
                source_ref VARCHAR NOT NULL,
                tags_json JSON NOT NULL
            )
            """
        )
        connection.execute(
            """
            CREATE OR REPLACE TABLE fact_knowledge_embedding (
                document_id VARCHAR PRIMARY KEY,
                embedding_model VARCHAR NOT NULL,
                dimensions INTEGER NOT NULL,
                vector DOUBLE[] NOT NULL
            )
            """
        )
        connection.executemany(
            "INSERT INTO dim_knowledge_document VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                (
                    document.document_id,
                    document.document_type,
                    document.title,
                    document.content,
                    document.origin,
                    document.shop_id,
                    document.product_id,
                    document.start_date,
                    document.end_date,
                    document.anomaly_metric,
                    document.cause_code,
                    document.source_ref,
                    json.dumps(document.tags, ensure_ascii=False),
                )
                for document in index.documents
            ],
        )
        connection.executemany(
            "INSERT INTO fact_knowledge_embedding VALUES (?, ?, ?, ?)",
            [
                (
                    document.document_id,
                    index.embedding_provider.model_name,
                    index.embedding_provider.dimensions,
                    vector,
                )
                for document, vector in zip(
                    index.documents, index.vectors, strict=True
                )
            ],
        )
