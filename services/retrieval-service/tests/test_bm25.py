from app.bm25 import BM25Index, tokenize


def test_tokenize_lowercases_and_drops_stopwords():
    assert tokenize("The Carrier is LATE") == ["carrier", "late"]


def test_ranks_matching_document_first():
    idx = BM25Index()
    idx.build([
        ("a", "parcel stuck at hub no scan"),
        ("b", "refund approval threshold for agents"),
        ("c", "address verification and reattempt"),
    ])
    hits = idx.search("refund approval", 3)
    assert len(hits) == 1
    assert hits[0][0] == "b"


def test_rare_terms_weigh_more():
    idx = BM25Index()
    idx.build([
        ("a", "carrier delay delay delay"),
        ("b", "carrier escalation"),
        ("c", "carrier carrier notice"),
    ])
    assert idx.search("carrier escalation", 3)[0][0] == "b"


def test_empty_index_and_stopword_only_queries():
    idx = BM25Index()
    assert idx.search("anything", 3) == []
    idx.build([("a", "some text here")])
    assert idx.search("the of", 3) == []