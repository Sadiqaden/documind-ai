"""Embedding providers.

- ``HashingEmbedder`` (default): deterministic, offline, dependency-free (numpy). Feature-hashes
  word unigrams/bigrams and character trigrams with sublinear TF weighting into a fixed-size,
  L2-normalised vector. It captures lexical overlap (incl. partial word matches) but not true
  synonyms - it is a pragmatic local default, not a semantic model.
- ``FastEmbedEmbedder`` (optional): real semantic embeddings (BAAI/bge-small-en-v1.5 by default)
  via the ``fastembed`` package (ONNX, CPU). Install with ``pip install '.[semantic]'``.

Changing provider requires re-indexing documents (the index stores the model name per document).
"""

from __future__ import annotations

import hashlib
import math
import re
from collections import Counter
from typing import Protocol

import numpy as np

_TOKEN = re.compile(r"[a-z0-9]+")
_STOPWORDS = frozenset(
    "a an the and or of to in on for with by is are was were be been it this that as at from "
    "what which who whom how why when where does do did can could should would will".split()
)


class Embedder(Protocol):
    name: str
    dim: int

    def embed_documents(self, texts: list[str]) -> np.ndarray: ...

    def embed_query(self, text: str) -> np.ndarray: ...


def tokenize(text: str) -> list[str]:
    return [t for t in _TOKEN.findall(text.lower()) if t not in _STOPWORDS]


class HashingEmbedder:
    def __init__(self, dim: int = 1024) -> None:
        self.dim = dim
        self.name = f"hash-v1-{dim}"

    def _bucket(self, feature: str) -> tuple[int, float]:
        h = hashlib.blake2b(feature.encode(), digest_size=8).digest()
        val = int.from_bytes(h, "little")
        return val % self.dim, (1.0 if (val >> 63) & 1 else -1.0)

    def _embed(self, text: str) -> np.ndarray:
        vec = np.zeros(self.dim, dtype=np.float32)
        tokens = tokenize(text)
        feats: Counter[str] = Counter()
        for t in tokens:
            feats[f"w:{t}"] += 2  # whole words weigh most
            padded = f"#{t}#"
            for i in range(len(padded) - 2):
                feats[f"c:{padded[i : i + 3]}"] += 1
        for a, b in zip(tokens, tokens[1:], strict=False):
            feats[f"b:{a}_{b}"] += 2
        for feat, count in feats.items():
            idx, sign = self._bucket(feat)
            vec[idx] += sign * (1.0 + math.log(count))
        norm = float(np.linalg.norm(vec))
        return vec / norm if norm > 0 else vec

    def embed_documents(self, texts: list[str]) -> np.ndarray:
        if not texts:
            return np.zeros((0, self.dim), dtype=np.float32)
        return np.vstack([self._embed(t) for t in texts])

    def embed_query(self, text: str) -> np.ndarray:
        return self._embed(text)


class FastEmbedEmbedder:  # pragma: no cover - optional heavy dependency
    def __init__(self, model_name: str) -> None:
        from fastembed import TextEmbedding

        self._model = TextEmbedding(model_name=model_name)
        self.name = f"fastembed:{model_name}"
        self.dim = len(next(iter(self._model.embed(["probe"]))))

    def _norm(self, arr: np.ndarray) -> np.ndarray:
        norms = np.linalg.norm(arr, axis=-1, keepdims=True)
        return (arr / np.where(norms == 0, 1, norms)).astype(np.float32)

    def embed_documents(self, texts: list[str]) -> np.ndarray:
        if not texts:
            return np.zeros((0, self.dim), dtype=np.float32)
        return self._norm(np.array(list(self._model.passage_embed(texts))))

    def embed_query(self, text: str) -> np.ndarray:
        return self._norm(np.array(list(self._model.query_embed([text])))[0])


def build_embedder(provider: str, fastembed_model: str) -> Embedder:
    if provider == "fastembed":
        return FastEmbedEmbedder(fastembed_model)
    return HashingEmbedder()
