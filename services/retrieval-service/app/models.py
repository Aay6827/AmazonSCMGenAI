from pydantic import BaseModel, Field


class ChunkIn(BaseModel):
    chunk_id: str = Field(min_length=1)
    doc_id: str = Field(min_length=1)
    title: str
    section: str = ""
    text: str = Field(min_length=1)
    version: str = "1"


class IndexRequest(BaseModel):
    chunks: list[ChunkIn] = Field(min_length=1)
    replace: bool = False


class SearchRequest(BaseModel):
    query: str = Field(min_length=1)
    k: int = Field(default=4, ge=1, le=20)


class Passage(ChunkIn):
    score: float
    citation: str