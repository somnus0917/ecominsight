from __future__ import annotations

from pathlib import Path

import duckdb

from ecom_insight.retrieval import (
    KnowledgeBuilder,
    KnowledgeDocument,
    KnowledgeIndex,
    LocalHashingEmbeddingProvider,
    RetrievalFilters,
)


def test_local_embedding_retrieves_relevant_rule() -> None:
    provider = LocalHashingEmbeddingProvider(dimensions=256)
    documents = [
        KnowledgeDocument(
            document_id="rule:R001",
            document_type="attribution_rule",
            title="流量下降",
            content="曝光人数和自然搜索流量下降",
            origin="public",
            cause_code="traffic_decline",
            source_ref="test",
        ),
        KnowledgeDocument(
            document_id="rule:R006",
            document_type="attribution_rule",
            title="投放效率下降",
            content="广告消耗上升但ROAS下降, 支付金额没有增长",
            origin="public",
            cause_code="ad_inefficiency",
            source_ref="test",
        ),
    ]
    index = KnowledgeIndex.build(documents, provider)

    hits = index.search(
        "广告消耗增加, ROAS降低",
        limit=1,
        filters=RetrievalFilters(document_types={"attribution_rule"}),
    )

    assert hits[0].document.document_id == "rule:R006"
    assert hits[0].score > 0


def test_knowledge_builder_publishes_only_safe_document_types(tmp_path: Path) -> None:
    database = tmp_path / "warehouse.duckdb"
    with duckdb.connect(str(database)):
        pass
    result = KnowledgeBuilder(
        database_path=database,
        metric_config_path=Path("configs/metrics.yaml"),
        rule_config_path=Path("configs/attribution_rules.yaml"),
        demo_root=Path("data/demo/generated"),
        artifact_root=tmp_path / "artifacts",
        embedding_provider=LocalHashingEmbeddingProvider(dimensions=128),
    ).run()

    assert result.document_type_counts["attribution_rule"] == 10
    assert result.document_type_counts["historical_case"] == 10
    with duckdb.connect(str(database), read_only=True) as connection:
        origins = connection.execute(
            "SELECT DISTINCT origin FROM dim_knowledge_document ORDER BY origin"
        ).fetchall()
        reviewed = connection.execute(
            "SELECT count(*) FROM dim_knowledge_document WHERE origin = 'real_reviewed'"
        ).fetchone()[0]
    assert origins == [("demo",), ("public",)]
    assert reviewed == 0
