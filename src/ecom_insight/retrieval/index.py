from __future__ import annotations

from collections.abc import Sequence

from ecom_insight.retrieval.embedding import EmbeddingProvider
from ecom_insight.retrieval.models import (
    KnowledgeDocument,
    RetrievalFilters,
    RetrievalHit,
)


def _dot(left: Sequence[float], right: Sequence[float]) -> float:
    if len(left) != len(right):
        raise ValueError("Embedding dimensions do not match")
    return float(sum(a * b for a, b in zip(left, right, strict=True)))


class KnowledgeIndex:
    def __init__(
        self,
        *,
        documents: list[KnowledgeDocument],
        vectors: list[list[float]],
        embedding_provider: EmbeddingProvider,
    ) -> None:
        if len(documents) != len(vectors):
            raise ValueError("Each knowledge document requires one embedding")
        if len({document.document_id for document in documents}) != len(documents):
            raise ValueError("Knowledge document IDs must be unique")
        for vector in vectors:
            if len(vector) != embedding_provider.dimensions:
                raise ValueError("Stored embedding dimensions do not match provider")
        self.documents = documents
        self.vectors = vectors
        self.embedding_provider = embedding_provider

    @classmethod
    def build(
        cls,
        documents: list[KnowledgeDocument],
        embedding_provider: EmbeddingProvider,
    ) -> KnowledgeIndex:
        vectors = embedding_provider.embed_documents(
            [f"{document.title}\n{document.content}" for document in documents]
        )
        return cls(
            documents=documents,
            vectors=vectors,
            embedding_provider=embedding_provider,
        )

    def search(
        self,
        query: str,
        *,
        limit: int = 5,
        filters: RetrievalFilters | None = None,
        minimum_score: float = 0.0,
    ) -> list[RetrievalHit]:
        if limit < 1:
            raise ValueError("Retrieval limit must be positive")
        active_filters = filters or RetrievalFilters()
        query_vector = self.embedding_provider.embed_query(query)
        scored: list[tuple[float, KnowledgeDocument]] = []
        for document, vector in zip(self.documents, self.vectors, strict=True):
            if not self._matches(document, active_filters):
                continue
            score = _dot(query_vector, vector)
            if score >= minimum_score:
                scored.append((score, document))
        scored.sort(key=lambda item: (-item[0], item[1].document_id))
        return [
            RetrievalHit(document=document, score=score, rank=rank)
            for rank, (score, document) in enumerate(scored[:limit], start=1)
        ]

    @staticmethod
    def _matches(
        document: KnowledgeDocument,
        filters: RetrievalFilters,
    ) -> bool:
        if document.document_id in filters.exclude_document_ids:
            return False
        if (
            filters.document_types is not None
            and document.document_type not in filters.document_types
        ):
            return False
        if filters.shop_id is not None and document.shop_id != filters.shop_id:
            return False
        if (
            filters.anomaly_metric is not None
            and document.anomaly_metric != filters.anomaly_metric
        ):
            return False
        return not (
            filters.cause_code is not None
            and document.cause_code != filters.cause_code
        )

