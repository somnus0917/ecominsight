from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import duckdb

from ecom_insight.retrieval.embedding import (
    EmbeddingProvider,
    LocalHashingEmbeddingProvider,
)
from ecom_insight.retrieval.index import KnowledgeIndex
from ecom_insight.retrieval.models import KnowledgeDocument


class DuckDBKnowledgeRepository:
    def __init__(
        self,
        *,
        database_path: Path,
        embedding_provider: EmbeddingProvider | None = None,
    ) -> None:
        self.database_path = database_path.resolve()
        self.embedding_provider = embedding_provider or LocalHashingEmbeddingProvider()

    def load(self) -> KnowledgeIndex:
        if not self.database_path.is_file():
            raise FileNotFoundError(self.database_path)
        with duckdb.connect(str(self.database_path), read_only=True) as connection:
            tables = {
                str(row[0])
                for row in connection.execute(
                    """
                    SELECT table_name
                    FROM information_schema.tables
                    WHERE table_name IN (
                        'dim_knowledge_document',
                        'fact_knowledge_embedding'
                    )
                    """
                ).fetchall()
            }
            if tables != {
                "dim_knowledge_document",
                "fact_knowledge_embedding",
            }:
                raise ValueError("Run Phase 6 knowledge build before retrieval")
            rows = connection.execute(
                """
                SELECT
                    d.document_id,
                    d.document_type,
                    d.title,
                    d.content,
                    d.origin,
                    d.shop_id,
                    d.product_id,
                    d.start_date,
                    d.end_date,
                    d.anomaly_metric,
                    d.cause_code,
                    d.source_ref,
                    d.tags_json,
                    e.embedding_model,
                    e.dimensions,
                    e.vector
                FROM dim_knowledge_document AS d
                JOIN fact_knowledge_embedding AS e USING (document_id)
                ORDER BY d.document_id
                """
            ).fetchall()
        documents: list[KnowledgeDocument] = []
        vectors: list[list[float]] = []
        for row in rows:
            embedding_model = str(row[13])
            dimensions = int(row[14])
            if embedding_model != self.embedding_provider.model_name:
                raise ValueError(
                    "Stored embedding model does not match configured provider"
                )
            if dimensions != self.embedding_provider.dimensions:
                raise ValueError(
                    "Stored embedding dimensions do not match configured provider"
                )
            tags_payload: Any = json.loads(str(row[12]))
            documents.append(
                KnowledgeDocument(
                    document_id=str(row[0]),
                    document_type=str(row[1]),  # type: ignore[arg-type]
                    title=str(row[2]),
                    content=str(row[3]),
                    origin=str(row[4]),  # type: ignore[arg-type]
                    shop_id=str(row[5]) if row[5] is not None else None,
                    product_id=str(row[6]) if row[6] is not None else None,
                    start_date=str(row[7]) if row[7] is not None else None,
                    end_date=str(row[8]) if row[8] is not None else None,
                    anomaly_metric=str(row[9]) if row[9] is not None else None,
                    cause_code=str(row[10]) if row[10] is not None else None,
                    source_ref=str(row[11]),
                    tags=list(tags_payload),
                )
            )
            vectors.append([float(value) for value in row[15]])
        return KnowledgeIndex(
            documents=documents,
            vectors=vectors,
            embedding_provider=self.embedding_provider,
        )

