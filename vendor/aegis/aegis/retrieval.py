"""Offline keyword retrieval (BM25).

Aegis "gets smarter" by recalling relevant snippets, lessons, and past
experiences and folding them into the prompt. Embeddings would be nicer, but
they need a model download and a vector store; BM25 needs neither and works
fine for the scale of a personal knowledge base.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from typing import Dict, Iterable, List, Sequence, Tuple

_TOKEN_RE = re.compile(r"[A-Za-z0-9_]+")


def tokenize(text: str) -> List[str]:
    return [t.lower() for t in _TOKEN_RE.findall(text or "")]


class BM25:
    """Standard Okapi BM25 over a small in-memory corpus."""

    def __init__(self, docs: Sequence[Tuple[str, str]], k1: float = 1.5, b: float = 0.75):
        """docs: sequence of (doc_id, text)."""
        self.k1 = k1
        self.b = b
        self.ids: List[str] = []
        self.tokens: List[List[str]] = []
        self.tf: List[Counter] = []
        self.df: Counter = Counter()

        for doc_id, text in docs:
            toks = tokenize(text)
            self.ids.append(doc_id)
            self.tokens.append(toks)
            counts = Counter(toks)
            self.tf.append(counts)
            for term in counts:
                self.df[term] += 1

        self.n = len(self.ids)
        self.avgdl = (sum(len(t) for t in self.tokens) / self.n) if self.n else 0.0

    def _idf(self, term: str) -> float:
        df = self.df.get(term, 0)
        return math.log(1 + (self.n - df + 0.5) / (df + 0.5))

    def search(self, query: str, k: int = 5) -> List[Tuple[str, float]]:
        if not self.n:
            return []
        q_terms = tokenize(query)
        if not q_terms:
            return []
        scores: List[Tuple[str, float]] = []
        for i, doc_id in enumerate(self.ids):
            dl = len(self.tokens[i]) or 1
            score = 0.0
            counts = self.tf[i]
            for term in q_terms:
                freq = counts.get(term, 0)
                if not freq:
                    continue
                idf = self._idf(term)
                denom = freq + self.k1 * (1 - self.b + self.b * dl / (self.avgdl or 1))
                score += idf * (freq * (self.k1 + 1)) / denom
            if score > 0:
                scores.append((doc_id, score))
        scores.sort(key=lambda x: x[1], reverse=True)
        return scores[:k]
