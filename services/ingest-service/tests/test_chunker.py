from app.chunker import chunk_document, parse_front_matter, split_sections, windows

DOC = "---\nid: d1\ntitle: Demo Doc\nversion: 2\n---\n# Demo Doc\n## Scope\nApplies to delays.\n## Actions\nEscalate after 48 hours.\n"


def test_front_matter_parsed():
    meta, body = parse_front_matter(DOC)
    assert meta == {"id": "d1", "title": "Demo Doc", "version": "2"}
    assert body.startswith("# Demo Doc")


def test_sections_split_on_headings_and_skip_empty():
    _, body = parse_front_matter(DOC)
    assert split_sections(body) == [("Scope", "Applies to delays."), ("Actions", "Escalate after 48 hours.")]


def test_chunk_ids_and_metadata():
    meta, chunks = chunk_document("fallback", DOC)
    assert meta["doc_id"] == "d1"
    assert [c.chunk_id for c in chunks] == ["d1#1", "d1#2"]
    assert chunks[1].section == "Actions" and chunks[1].version == "2"


def test_crlf_and_bom_are_normalised():
    meta, chunks = chunk_document("fallback", "\ufeff" + DOC.replace("\n", "\r\n"))
    assert meta["doc_id"] == "d1"
    assert len(chunks) == 2


def test_missing_front_matter_uses_default_id():
    meta, chunks = chunk_document("my-file", "## Only\nSome text.")
    assert meta["doc_id"] == "my-file"
    assert chunks[0].chunk_id == "my-file#1"


def test_long_section_is_windowed_with_overlap():
    text = " ".join(f"w{i}" for i in range(200))
    parts = windows(text, max_words=90, overlap=20)
    assert len(parts) == 3
    assert all(len(p.split()) <= 90 for p in parts)
    assert parts[0].split()[-20:] == parts[1].split()[:20]