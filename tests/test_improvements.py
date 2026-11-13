import json
import sqlite3
from types import SimpleNamespace

import pytest

from jurisia import search, prepare, evaluation, rag
from jurisia.audit import summarize_synthesis


def test_invalid_index_preserves_active_pointer(tmp_path, monkeypatch):
    monkeypatch.setattr(search, "VECTOR", tmp_path)
    pointer = tmp_path / "active_index.json"
    pointer.write_text('{"collection":"original"}')
    for kwargs in ({"size": 0}, {"overlap": 70}, {"limit": -1}, {"batch_size": 0}):
        with pytest.raises(ValueError):
            search.index(**kwargs)
    assert json.loads(pointer.read_text())["collection"] == "original"


def test_index_embedding_failure_preserves_active_index(tmp_path, monkeypatch):
    path = tmp_path / "docs.sqlite3"
    db = prepare.connect(path)
    db.execute("INSERT INTO documents(id,ementa,raw_json,dataset,resource,resource_url) VALUES('1','texto','{}','d','r','u')")
    db.commit()
    db.close()
    pointer = tmp_path / "active_index.json"
    pointer.write_text('{"collection":"original"}')
    class BrokenModel:
        def encode(self, *args, **kwargs):
            raise RuntimeError("simulated embedding failure")
    client = SimpleNamespace(get_or_create_collection=lambda *a, **k: object())
    import sys
    monkeypatch.setitem(sys.modules, "chromadb", SimpleNamespace(PersistentClient=lambda **k: client))
    monkeypatch.setattr(search, "DB", path)
    monkeypatch.setattr(search, "VECTOR", tmp_path)
    monkeypatch.setattr(search, "model", lambda: BrokenModel())
    with pytest.raises(RuntimeError, match="simulated"):
        search.index()
    assert json.loads(pointer.read_text())["collection"] == "original"


def test_changed_resource_is_imported_again(tmp_path, monkeypatch):
    folder = tmp_path / "dataset"
    folder.mkdir()
    file = folder / "20200101.json"
    manifest = {"dataset": "d", "resources": [{"name": file.name, "url": "https://example.org"}]}
    (folder / "manifest.json").write_text(json.dumps(manifest))
    monkeypatch.setattr(prepare, "RAW", tmp_path)
    path = tmp_path / "docs.sqlite3"
    file.write_text(json.dumps([{"id": "001", "ementa": "primeira"}]))
    assert prepare.import_all(path)["records"] == 1
    assert prepare.import_all(path)["records"] == 0
    file.write_text(json.dumps([{"id": "001", "ementa": "atualizada"}]))
    assert prepare.import_all(path)["records"] == 1
    assert prepare.get_documents(["001"], path)["001"]["ementa"] == "atualizada"


def test_lexical_index_tracks_database_changes(tmp_path, monkeypatch):
    path = tmp_path / "docs.sqlite3"
    db = prepare.connect(path)
    db.execute("INSERT INTO documents(id,ementa,raw_json,dataset,resource,resource_url) VALUES('1','responsabilidade médica','{}','d','r','u')")
    db.commit()
    monkeypatch.setattr(search, "DB", path)
    monkeypatch.setattr(search, "get_documents", lambda ids: prepare.get_documents(ids, path))
    assert search.lexical_search("medica")[0]["id"] == "1"
    db.execute("UPDATE documents SET ementa='contratos bancários' WHERE id='1'")
    db.commit()
    assert search.lexical_search("medica") == []
    assert search.lexical_search("contratos")[0]["id"] == "1"
    db.close()


def test_evaluation_separates_unanswerable_queries(tmp_path, monkeypatch):
    file = tmp_path / "questions.csv"
    file.write_text("question,relevant_ids,category\nknown,1,simples\nunknown,,sem_resposta\n", encoding="utf-8")
    monkeypatch.setattr(evaluation, "search", lambda q, **k: [{"id": "1"}] if q == "known" else [])
    result = evaluation.evaluate(file, k=2)
    assert result["precision_at_k"] == 0.5
    assert result["recall_at_k"] == 1
    assert result["n"] == 1
    assert result["abstention_rate"] == 1


def test_synthesis_review_requires_supporting_evidence(tmp_path):
    file = tmp_path / "review.csv"
    file.write_text("claim,status,evidence\nregra,suportada,\n", encoding="utf-8")
    with pytest.raises(ValueError, match="evidence"):
        summarize_synthesis(file)
    file.write_text("claim,status,evidence\nregra,suportada,trecho da ementa\n", encoding="utf-8")
    assert summarize_synthesis(file)["supported_rate"] == 1


def test_synthesis_time_is_not_added_twice(tmp_path, monkeypatch):
    path = tmp_path / "docs.sqlite3"
    db = prepare.connect(path)
    db.execute("INSERT INTO questions(id,question,response_seconds,search_seconds,mode) VALUES(1,'q',2,2,'retrieval')")
    db.commit()
    monkeypatch.setattr(rag, "DB", path)
    rag.record_synthesis(1, 3)
    rag.record_synthesis(1, 4)
    assert db.execute("SELECT response_seconds,synthesis_seconds FROM questions").fetchone()[:] == (6, 4)
    db.close()


def test_search_validates_filters_before_loading_index():
    with pytest.raises(ValueError):
        search.search("q", k=0)
    with pytest.raises(ValueError):
        search.search("q", year_from=2025, year_to=2020)


def test_sync_downloads_changed_revision(tmp_path, monkeypatch):
    from jurisia import download
    monkeypatch.setattr(download, "RAW", tmp_path)
    revision = ["one"]
    monkeypatch.setattr(download, "resources", lambda slug: [
        {"name": "20200101.json", "url": "https://example.org/data", "revision": revision.copy()}])
    calls = []
    def fetch(item, target):
        calls.append(item["revision"])
        target.write_text("[]")
    monkeypatch.setattr(download, "_download", fetch)
    download.sync(["test"])
    download.sync(["test"])
    assert len(calls) == 1
    revision[0] = "two"
    download.sync(["test"])
    assert len(calls) == 2


def test_search_applies_date_and_body_filters(monkeypatch):
    class Vector:
        def tolist(self):
            return [[0.1]]
    monkeypatch.setattr(search, "model", lambda: SimpleNamespace(encode=lambda *a, **k: Vector()))
    observed = {}
    class Collection:
        metadata = {"embedding_model": search.EMBEDDING_MODEL}
        def count(self):
            return 1
        def query(self, **kwargs):
            observed.update(kwargs)
            return {"documents": [[]], "metadatas": [[]], "distances": [[]]}
    monkeypatch.setattr(search, "collection", Collection)
    assert search.search("pergunta", body="TURMA", year_from=2020, year_to=2025) == []
    assert observed["where"] == {"$and": [{"court_body": "TURMA"},
        {"decision_date": {"$gte": 20200101}}, {"decision_date": {"$lte": 20251231}}]}
