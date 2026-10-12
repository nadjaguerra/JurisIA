import json
from pathlib import Path
from zipfile import ZipFile

import pytest

from jurisia.chunking import chunks
from jurisia.prepare import _records, connect
from jurisia.search import rerank


def test_zip_and_json_have_same_record_interface(tmp_path):
    records = [{"id": "001", "ementa": "Responsabilidade por erro médico."}]
    plain = tmp_path / "20220531.json"
    plain.write_text(json.dumps(records), encoding="utf-8")
    zipped = tmp_path / "20220508.zip"
    with ZipFile(zipped, "w") as archive:
        archive.writestr("20220508.json", json.dumps(records))
    assert list(_records(plain)) == list(_records(zipped)) == records


def test_chunk_overlap_and_empty():
    assert chunks("", 4, 1) == []
    assert chunks("a b c d e f", 4, 1) == ["a b c d", "d e f"]
    with pytest.raises(ValueError):
        chunks("a b", 4, 4)


def test_database_keeps_unique_document_ids(tmp_path):
    db = connect(tmp_path / "unit.sqlite3")
    db.execute("""
      INSERT INTO documents VALUES
      ('001','7','REsp','TERCEIRA TURMA','R','20260501','','texto','','{}','x','a','https://example.org')
    """)
    with pytest.raises(Exception):
        db.execute("""
          INSERT INTO documents VALUES
          ('001','8','REsp','TERCEIRA TURMA','R','20260502','','texto','','{}','x','b','https://example.org')
        """)
    db.close()


def test_rerank_prefers_more_question_terms_at_equal_similarity():
    items = [{"id": "1", "snippet": "erro médico", "similarity": 0.6},
             {"id": "2", "snippet": "erro médico responsabilidade civil",
              "similarity": 0.6}]
    assert rerank("responsabilidade civil por erro médico", items)[0]["id"] == "2"
