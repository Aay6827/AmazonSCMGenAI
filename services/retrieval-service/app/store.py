import threading

from app.bm25 import BM25Index
from app.models import ChunkIn, Passage


class ChunkStore:
    def __init__(self):
        self._chunks: dict[str, ChunkIn] = {}
        self._index = BM25Index()
        self._lock = threading.Lock()

    def add(self, chunks: list[ChunkIn], replace: bool = False) -> int:
        with self._lock:
            if replace:
                self._chunks.clear()
            for c in chunks:
                self._chunks[c.chunk_id] = c
            self._index.build(
                [(c.chunk_id, f"{c.title} {c.section} {c.text}") for c in self._chunks.values()]
            )
            return len(chunks)

    def search(self, query: str, k: int) -> list[Passage]:
        with self._lock:
            hits = self._index.search(query, k)
            return [
                Passage(
                    **self._chunks[cid].model_dump(),
                    score=round(score, 4),
                    citation=f"[SOURCE:{cid}]",
                )
                for cid, score in hits
            ]

    def doc_count(self) -> int:
        return len({c.doc_id for c in self._chunks.values()})

    def __len__(self) -> int:
        return len(self._chunks)