"""Local retrieval for sanitized cases, definitions and attribution rules."""

from ecom_insight.retrieval.builder import KnowledgeBuilder, KnowledgeBuildResult
from ecom_insight.retrieval.embedding import (
    EmbeddingProvider,
    LocalHashingEmbeddingProvider,
)
from ecom_insight.retrieval.index import KnowledgeIndex
from ecom_insight.retrieval.models import (
    KnowledgeDocument,
    RetrievalFilters,
    RetrievalHit,
)

__all__ = [
    "EmbeddingProvider",
    "KnowledgeBuildResult",
    "KnowledgeBuilder",
    "KnowledgeDocument",
    "KnowledgeIndex",
    "LocalHashingEmbeddingProvider",
    "RetrievalFilters",
    "RetrievalHit",
]
