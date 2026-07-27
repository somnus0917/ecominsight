from __future__ import annotations

from typing import Protocol

from sklearn.feature_extraction.text import HashingVectorizer


class EmbeddingProvider(Protocol):
    @property
    def model_name(self) -> str: ...

    @property
    def dimensions(self) -> int: ...

    def embed_documents(self, texts: list[str]) -> list[list[float]]: ...

    def embed_query(self, text: str) -> list[float]: ...


class LocalHashingEmbeddingProvider:
    """Training-free local character n-gram embeddings for safe offline retrieval."""

    def __init__(self, dimensions: int = 512) -> None:
        if dimensions < 64:
            raise ValueError("Embedding dimensions must be at least 64")
        self._dimensions = dimensions
        self._vectorizer = HashingVectorizer(
            n_features=dimensions,
            analyzer="char",
            ngram_range=(2, 4),
            alternate_sign=False,
            norm="l2",
            lowercase=True,
        )

    @property
    def model_name(self) -> str:
        return f"local_hashing_char_2_4_{self._dimensions}"

    @property
    def dimensions(self) -> int:
        return self._dimensions

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        matrix = self._vectorizer.transform(texts)
        return [
            [float(value) for value in row]
            for row in matrix.toarray()
        ]

    def embed_query(self, text: str) -> list[float]:
        return self.embed_documents([text])[0]
