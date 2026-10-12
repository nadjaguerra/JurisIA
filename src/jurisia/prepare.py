"""Importa os espelhos e guarda proveniência e documentos no SQLite."""

import json
import sqlite3
from pathlib import Path
from zipfile import ZipFile

from .config import DB, RAW


def connect(path: Path = DB) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(path)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA journal_mode=WAL")
    db.executescript("""
        CREATE TABLE IF NOT EXISTS documents (
          id TEXT PRIMARY KEY, process_number TEXT, process_class TEXT,
          court_body TEXT, rapporteur TEXT, decision_date TEXT,
          publication_date TEXT, ementa TEXT, extra TEXT, raw_json TEXT NOT NULL,
          dataset TEXT NOT NULL, resource TEXT NOT NULL, resource_url TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_docs_date ON documents(decision_date);
        CREATE INDEX IF NOT EXISTS idx_docs_body ON documents(court_body);
        CREATE TABLE IF NOT EXISTS imported_resources (
          dataset TEXT NOT NULL, resource TEXT NOT NULL,
          PRIMARY KEY(dataset, resource)
        );
        CREATE TABLE IF NOT EXISTS questions (
          id INTEGER PRIMARY KEY, created_at TEXT DEFAULT CURRENT_TIMESTAMP,
          question TEXT NOT NULL, response_seconds REAL, retrieved INTEGER,
          mode TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS feedback (
          id INTEGER PRIMARY KEY, question_id INTEGER,
          useful INTEGER, clarity INTEGER, relevance INTEGER,
          confidence INTEGER, usability INTEGER, satisfaction INTEGER,
          reuse TEXT, comment TEXT,
          created_at TEXT DEFAULT CURRENT_TIMESTAMP,
          FOREIGN KEY(question_id) REFERENCES questions(id)
        );
    """)
    return db


def _date(value) -> str:
    text = str(value or "")
    return text[:8] if len(text) >= 8 and text[:8].isdigit() else ""


def _records(path: Path):
    if path.suffix == ".zip":
        with ZipFile(path) as z:
            for member in sorted(z.namelist()):
                if member.endswith(".json") and not member.startswith("__MACOSX/"):
                    with z.open(member) as file:
                        records = json.load(file)
                    if not isinstance(records, list):
                        raise ValueError(f"Esperava lista: {path.name}/{member}")
                    yield from records
    else:
        with path.open(encoding="utf-8-sig") as file:
            records = json.load(file)
        if not isinstance(records, list):
            raise ValueError(f"Esperava lista: {path.name}")
        yield from records


def import_all(path: Path = DB) -> dict:
    db = connect(path)
    stats = {"resources": 0, "records": 0, "skipped_ids": 0}
    manifests = sorted(RAW.glob("*/manifest.json"))
    if not manifests:
        raise FileNotFoundError("Nenhum manifesto. Rode `jurisia sync` primeiro.")
    # A ordem cronológica faz a versão mais nova do mesmo ID prevalecer.
    for manifest_path in manifests:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        dataset = manifest["dataset"]
        for item in sorted(manifest["resources"], key=lambda r: r["name"]):
            name = item["name"]
            if db.execute("SELECT 1 FROM imported_resources WHERE dataset=? AND resource=?",
                          (dataset, name)).fetchone():
                continue
            file = manifest_path.parent / name
            if not file.exists():
                raise FileNotFoundError(file)
            with db:
                for row in _records(file):
                    ident = str(row.get("id") or "").strip()
                    if not ident:
                        stats["skipped_ids"] += 1
                        continue
                    db.execute("""
                        INSERT INTO documents VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
                        ON CONFLICT(id) DO UPDATE SET
                          process_number=excluded.process_number,
                          process_class=excluded.process_class,
                          court_body=excluded.court_body,
                          rapporteur=excluded.rapporteur,
                          decision_date=excluded.decision_date,
                          publication_date=excluded.publication_date,
                          ementa=excluded.ementa, extra=excluded.extra,
                          raw_json=excluded.raw_json, dataset=excluded.dataset,
                          resource=excluded.resource, resource_url=excluded.resource_url
                    """, (
                        ident, str(row.get("numeroProcesso") or ""),
                        str(row.get("siglaClasse") or ""),
                        str(row.get("nomeOrgaoJulgador") or ""),
                        str(row.get("ministroRelator") or ""),
                        _date(row.get("dataDecisao")),
                        str(row.get("dataPublicacao") or ""),
                        str(row.get("ementa") or ""),
                        str(row.get("informacoesComplementares") or ""),
                        json.dumps(row, ensure_ascii=False), dataset,
                        name, item["url"],
                    ))
                    stats["records"] += 1
                db.execute("INSERT INTO imported_resources VALUES (?,?)", (dataset, name))
            stats["resources"] += 1
            print(f"Importado: {dataset}/{name}", flush=True)
    stats["unique"] = db.execute("SELECT COUNT(*) FROM documents").fetchone()[0]
    stats["with_ementa"] = db.execute(
        "SELECT COUNT(*) FROM documents WHERE LENGTH(TRIM(ementa))>0"
    ).fetchone()[0]
    db.close()
    return stats


def get_documents(ids: list[str], path: Path = DB) -> dict[str, dict]:
    if not ids or not path.exists():
        return {}
    db = sqlite3.connect(path)
    db.row_factory = sqlite3.Row
    marks = ",".join("?" for _ in ids)
    rows = db.execute(f"SELECT * FROM documents WHERE id IN ({marks})", ids).fetchall()
    db.close()
    return {row["id"]: dict(row) for row in rows}
