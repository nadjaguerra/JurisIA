from jurisia import prepare, rag, search
from jurisia.explore import distribution, rank_comparison


def test_rank_comparison_keeps_positions_and_groups():
    def hit(ident, year):
        return {"id": ident, "document": {"decision_date": year, "process_number": ident}}

    a, b, c = hit("1", "20230101"), hit("2", None), hit("3", "20240101")
    assert distribution([a, b], "decision_date") == {"2023": 1, "Não informado": 1}
    rows = rank_comparison([a, b], [c, a])
    assert [(r["ID"], r["Palavras"], r["Significado"], r["Presença"]) for r in rows] == [
        ("1", 1, 2, "Nas duas"), ("2", 2, None, "Só palavras"), ("3", None, 1, "Só significado")]


def test_lexical_filters_before_applying_limit(tmp_path, monkeypatch):
    path = tmp_path / "test.sqlite3"
    monkeypatch.setattr(search, "DB", path)
    monkeypatch.setattr(search, "get_documents", lambda ids: prepare.get_documents(ids, path))
    db = prepare.connect(path)
    db.executemany(
        "INSERT INTO documents(id,ementa,court_body,decision_date,raw_json,dataset,resource,resource_url) VALUES(?,?,?,?,'{}','d','r','u')",
        [("1", "contrato", "A", ""), ("2", "contrato", "B", "20230101"),
         ("3", "contrato", "A", "20220101"), ("4", "contrato", "A", "20240101")])
    db.commit()
    db.close()
    assert [hit["id"] for hit in search.lexical_search("contrato", 1, "A", 2023, 2025)] == ["4"]
    assert [hit["id"] for hit in search.lexical_search("contrato", 5, "A", year_to=2022)] == ["3"]
    pages = [search.lexical_search("contrato", 1, "A", newest_first=True, offset=i)
             for i in range(4)]
    assert [[hit["id"] for hit in page] for page in pages] == [["4"], ["3"], ["1"], []]


def test_semantic_pages_order_by_date_before_slicing(monkeypatch):
    from types import SimpleNamespace

    def query(**kwargs):
        return {"documents": [["texto"] * 4],
                "metadatas": [[{"document_id": ident, "position": pos, "decision_date": date}
                               for ident, pos, date in [("a", 0, 20200101), ("b", 0, 20240101),
                                                        ("b", 1, 20240101), ("c", 0, 20230101)]]],
                "distances": [[.1, .2, .3, .4]]}

    monkeypatch.setattr(search, "_embedding", lambda _: [[1]])
    monkeypatch.setattr(search, "collection", lambda: SimpleNamespace(count=lambda: 4, metadata={}, query=query))
    monkeypatch.setattr(search, "get_documents", lambda ids: {ident: {"id": ident} for ident in ids})
    pages = [search.search("texto", k=1, newest_first=True, offset=i) for i in range(4)]
    assert [[hit["id"] for hit in page] for page in pages] == [["b"], ["c"], ["a"], []]


def test_feedback_replaces_previous_vote(tmp_path, monkeypatch):
    path = tmp_path / "test.sqlite3"
    monkeypatch.setattr(rag, "DB", path)
    db = prepare.connect(path)
    with db:
        db.execute("INSERT INTO questions(id,question,mode) VALUES(1,'consulta','retrieval')")
    rag.record_result_feedback(1, "77", 2, "lexical", True)
    rag.record_result_feedback(1, "77", 2, "lexical", False)
    assert [tuple(row) for row in db.execute("SELECT * FROM result_feedback")] == [(1, "77", 2, "lexical", 0)]
    db.close()
