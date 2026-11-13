"""Empacota a base textual enquanto o índice vetorial é construído."""
import hashlib
import json
import os
import sqlite3
from contextlib import closing
from zipfile import ZIP_DEFLATED, ZipFile

from jurisia.config import DB, ROOT
from jurisia.search import lexical_search

query = "responsabilidade civil por erro médico"
pages = [lexical_search(query, k=5, newest_first=True, offset=i) for i in (0, 5)]
hits = pages[0] + pages[1]
dates = [hit["document"]["decision_date"] or "" for hit in hits]
if len({hit["id"] for hit in hits}) != 10 or dates != sorted(dates, reverse=True):
    raise RuntimeError("A busca e a paginação não passaram na verificação.")
with closing(sqlite3.connect(DB)) as db:
    if db.execute("PRAGMA quick_check").fetchone()[0] != "ok":
        raise RuntimeError("SQLite inválido.")
    documents = db.execute("SELECT COUNT(*) FROM documents").fetchone()[0]
    if documents < 68308:
        raise RuntimeError("Corpus abaixo dos 68.308 documentos auditados.")
    for table in ("questions", "feedback", "result_feedback"):
        if db.execute(f"SELECT EXISTS(SELECT 1 FROM {table})").fetchone()[0]:
            raise RuntimeError(f"Dados de usuários encontrados em {table}.")
    db.execute("PRAGMA wal_checkpoint(TRUNCATE)")
out = ROOT / "cloud-output"
out.mkdir(exist_ok=True)
archive = out / "jurisia-data.zip"
with ZipFile(archive, "w", compression=ZIP_DEFLATED, compresslevel=3) as zipped:
    zipped.write(DB, DB.relative_to(ROOT))
with archive.open("rb") as file:
    digest = hashlib.file_digest(file, "sha256").hexdigest()
manifest = {"version": os.environ["SNAPSHOT_VERSION"], "sha256": digest,
            "documents": documents, "lexical_only": True}
(out / "jurisia-manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
print(json.dumps(manifest))
