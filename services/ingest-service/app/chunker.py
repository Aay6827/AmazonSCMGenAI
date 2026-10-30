import re
from dataclasses import asdict, dataclass

MAX_WORDS = 90
OVERLAP = 20
_HEADING = re.compile(r"^(#{1,3})\s+(.+?)\s*$")


@dataclass
class Chunk:
    chunk_id: str
    doc_id: str
    title: str
    section: str
    text: str
    version: str

    def to_dict(self) -> dict:
        return asdict(self)


def parse_front_matter(raw: str) -> tuple[dict, str]:
    match = re.match(r"\A---\s*\n(.*?)\n---\s*\n", raw, re.DOTALL)
    if not match:
        return {}, raw
    meta = {}
    for line in match.group(1).splitlines():
        if ":" in line:
            key, value = line.split(":", 1)
            meta[key.strip().lower()] = value.strip()
    return meta, raw[match.end():]


def split_sections(body: str) -> list[tuple[str, str]]:
    sections: list[tuple[str, str]] = []
    current, buf = "Overview", []
    for line in body.split("\n"):
        m = _HEADING.match(line)
        if m:
            text = "\n".join(buf).strip()
            if text:
                sections.append((current, text))
            current, buf = m.group(2), []
        else:
            buf.append(line)
    text = "\n".join(buf).strip()
    if text:
        sections.append((current, text))
    return sections


def windows(text: str, max_words: int = MAX_WORDS, overlap: int = OVERLAP) -> list[str]:
    words = text.split()
    if len(words) <= max_words:
        return [text.strip()]
    step = max_words - overlap
    out, i = [], 0
    while i < len(words):
        out.append(" ".join(words[i : i + max_words]))
        if i + max_words >= len(words):
            break
        i += step
    return out


def chunk_document(default_id: str, raw: str) -> tuple[dict, list[Chunk]]:
    raw = raw.replace("\r\n", "\n").lstrip("\ufeff")
    meta, body = parse_front_matter(raw)
    doc_id = meta.get("id") or default_id
    title = meta.get("title") or doc_id
    version = meta.get("version", "1")
    chunks: list[Chunk] = []
    n = 0
    for section, text in split_sections(body):
        for piece in windows(text):
            n += 1
            chunks.append(Chunk(f"{doc_id}#{n}", doc_id, title, section, piece, version))
    return {"doc_id": doc_id, "title": title, "version": version}, chunks