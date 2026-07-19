from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


def create_embeddings():
    import torch
    from langchain_huggingface import HuggingFaceEmbeddings

    from config.config import Config

    model_kwargs = {
        "device": Config.EMBEDDING_DEVICE,
        "local_files_only": Config.EMBEDDING_LOCAL_FILES_ONLY,
    }
    if Config.EMBEDDING_DEVICE == "cuda" and torch.cuda.is_available():
        model_kwargs["model_kwargs"] = {"torch_dtype": torch.float16}
    return HuggingFaceEmbeddings(
        model_name=Config.EMBEDDING_MODEL,
        model_kwargs=model_kwargs,
        encode_kwargs={"batch_size": 8},
    )


@dataclass(frozen=True)
class SemanticDocument:
    document_id: str
    text: str
    metadata: dict[str, str | int | float | bool]


@dataclass(frozen=True)
class SemanticHit:
    document_id: str
    score: float


class SemanticIndex(Protocol):
    available: bool

    def ensure_collection(
        self, name: str, fingerprint: str, documents: list[SemanticDocument]
    ) -> None: ...

    def search(
        self,
        collection: str,
        text: str,
        limit: int,
        allowed_ids: list[str] | None = None,
    ) -> list[SemanticHit]: ...

    def embed_documents(self, texts: list[str]) -> list[list[float]]: ...


class InMemorySemanticIndex:
    """Deterministic semantic seam for tests and keyword-only fallback."""

    available = True

    def __init__(self) -> None:
        self._collections: dict[str, list[SemanticDocument]] = {}
        self._fingerprints: dict[str, str] = {}

    def ensure_collection(
        self, name: str, fingerprint: str, documents: list[SemanticDocument]
    ) -> None:
        if self._fingerprints.get(name) == fingerprint:
            return
        self._collections[name] = list(documents)
        self._fingerprints[name] = fingerprint

    def search(
        self,
        collection: str,
        text: str,
        limit: int,
        allowed_ids: list[str] | None = None,
    ) -> list[SemanticHit]:
        allowed = set(allowed_ids) if allowed_ids is not None else None
        query_tokens = set(text.casefold().replace("-", " ").split())
        hits = []
        for document in self._collections.get(collection, []):
            if allowed is not None and document.document_id not in allowed:
                continue
            tokens = set(document.text.casefold().replace("-", " ").split())
            score = len(query_tokens & tokens) / max(len(query_tokens), 1)
            hits.append(SemanticHit(document.document_id, score))
        return sorted(hits, key=lambda hit: hit.score, reverse=True)[:limit]

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [[float(len(text)), float(len(text.split()))] for text in texts]


class ChromaSemanticIndex:
    available = True

    def __init__(self, persist_directory: str | Path, embeddings) -> None:
        import chromadb

        self._client = chromadb.PersistentClient(path=str(persist_directory))
        self._embeddings = embeddings

    def ensure_collection(
        self, name: str, fingerprint: str, documents: list[SemanticDocument]
    ) -> None:
        try:
            collection = self._client.get_collection(name)
            metadata = collection.metadata or {}
            if metadata.get("fingerprint") == fingerprint and collection.count() == len(documents):
                return
            self._client.delete_collection(name)
        except Exception:
            pass

        collection = self._client.create_collection(
            name=name,
            metadata={"fingerprint": fingerprint, "hnsw:space": "cosine"},
        )
        batch_size = 256
        for start in range(0, len(documents), batch_size):
            batch = documents[start : start + batch_size]
            texts = [document.text for document in batch]
            collection.add(
                ids=[document.document_id for document in batch],
                documents=texts,
                metadatas=[document.metadata for document in batch],
                embeddings=self._embeddings.embed_documents(texts),
            )

    def search(
        self,
        collection: str,
        text: str,
        limit: int,
        allowed_ids: list[str] | None = None,
    ) -> list[SemanticHit]:
        if not text.strip() or allowed_ids == []:
            return []
        where = {"record_id": {"$in": allowed_ids}} if allowed_ids is not None else None
        result = self._client.get_collection(collection).query(
            query_embeddings=[self._embeddings.embed_query(text)],
            n_results=max(1, min(limit, len(allowed_ids) if allowed_ids is not None else limit)),
            where=where,
            include=["distances"],
        )
        ids = result.get("ids", [[]])[0]
        distances = result.get("distances", [[]])[0]
        return [
            SemanticHit(document_id, max(0.0, 1.0 - float(distance)))
            for document_id, distance in zip(ids, distances)
        ]

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return self._embeddings.embed_documents(texts)
