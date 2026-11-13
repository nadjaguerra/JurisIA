"""Valida e empacota somente os dados gerados por um runner limpo."""
import hashlib
import json
import os
import sqlite3
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

from jurisia.config import DB, ROOT, VECTOR
from jurisia.search import collection, lexical_search, search


def main():
    destination = ROOT / "cloud-output"
    destination.mkdir(exist_ok=True)
    query = "responsabilidade civil por erro médico"
    lexical = lexical_search(query, newest_first=True)
    semantic = search(query, min_similarity=0.30, newest_first=True)
    if not lexical or not semantic:
        raise RuntimeError("A base não passou nas consultas de verificação.")
    with sqlite3.connect(DB) as db:
        if db.execute("PRAGMA quick_check").fetchone()[0] != "ok":
            raise RuntimeError("SQLite inválido.")
        for table in ("questions", "feedback", "result_feedback"):
            if db.execute(f"SELECT EXISTS(SELECT 1 FROM {table})").fetchone()[0]:
                raise RuntimeError(f"Dados de usuários encontrados em {table}.")
        documents, with_text = db.execute(
            "SELECT COUNT(*), SUM(LENGTH(TRIM(ementa)) > 0) FROM documents"
        ).fetchone()
        if documents < 68308:
            raise RuntimeError("A coleta ficou abaixo do corpus local auditado (68.308 documentos).")
        active = json.loads((VECTOR / "active_index.json").read_text(encoding="utf-8"))
        if active["documents"] != with_text or active["chunks"] != collection().count():
            raise RuntimeError("O índice não cobre todas as ementas.")
        db.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    archive = destination / "jurisia-data.zip"
    with ZipFile(archive, "w", compression=ZIP_DEFLATED, compresslevel=3) as zipped:
        zipped.write(DB, DB.relative_to(ROOT))
        for file in VECTOR.rglob("*"):
            if file.is_file():
                zipped.write(file, file.relative_to(ROOT))
    with archive.open("rb") as file:
        digest = hashlib.file_digest(file, "sha256").hexdigest()
    manifest = {"version": os.environ["SNAPSHOT_VERSION"], "sha256": digest,
                "documents": documents, "indexed_documents": with_text, "chunks": active["chunks"]}
    (destination / "jurisia-manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(json.dumps(manifest))


if __name__ == "__main__":
    main()
