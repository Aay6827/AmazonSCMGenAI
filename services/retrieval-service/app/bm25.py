import math
import re
from collections import Counter

STOPWORDS = {
    "the", "a", "an", "and", "or", "of", "to", "in", "is", "for", "on",
    "with", "at", "by", "be", "it", "as", "are", "this", "that",
}


def tokenize(text: str) -> list[str]:
    return [t for t in re.findall(r"[a-z0-9]+", text.lower()) if t not in STOPWORDS]


class BM25Index:
    def __init__(self, k1: float = 1.5, b: float = 0.75):
        self.k1 = k1
        self.b = b
        self._ids: list[str] = []
        self._tf: list[Counter] = []
        self._len: list[int] = []
        self._df: Counter = Counter()
        self._avgdl = 0.0

    def build(self, docs: list[tuple[str, str]]) -> None:
        self._ids, self._tf, self._len, self._df = [], [], [], Counter()
        for doc_id, text in docs:
            tokens = tokenize(text)
            tf = Counter(tokens)
            self._ids.append(doc_id)
            self._tf.append(tf)
            self._len.append(len(tokens))
            self._df.update(tf.keys())
        self._avgdl = (sum(self._len) / len(self._len)) if self._len else 0.0

    def search(self, query: str, k: int = 4) -> list[tuple[str, float]]:
        terms = set(tokenize(query))
        n = len(self._ids)
        if not terms or n == 0:
            return []
        scored = []
        for i, tf in enumerate(self._tf):
            score = 0.0
            for term in terms:
                freq = tf.get(term, 0)
                if not freq:
                    continue
                df = self._df[term]
                idf = math.log(1 + (n - df + 0.5) / (df + 0.5))
                denom = freq + self.k1 * (1 - self.b + self.b * self._len[i] / (self._avgdl or 1))
                score += idf * freq * (self.k1 + 1) / denom
            if score > 0:
                scored.append((self._ids[i], score))
        scored.sort(key=lambda x: -x[1])
        return scored[:k]