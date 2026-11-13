"""Relatório reproduzível da base local, sem atribuir qualidade jurídica."""
import json
import sqlite3
import platform
from datetime import datetime, timezone
from importlib.metadata import version, PackageNotFoundError
from pathlib import Path

from .config import DB, VECTOR


def audit(destination: Path) -> dict:
    with sqlite3.connect(f"file:{DB.as_posix()}?mode=ro", uri=True) as db:
        total, empty, earliest, latest = db.execute(
            "SELECT COUNT(*),SUM(CASE WHEN LENGTH(TRIM(COALESCE(ementa,'')))=0 THEN 1 ELSE 0 END),MIN(NULLIF(decision_date,'')),MAX(NULLIF(decision_date,'')) FROM documents").fetchone()
        bodies = dict(db.execute("SELECT court_body,COUNT(*) FROM documents GROUP BY court_body"))
        resources = db.execute("SELECT COUNT(*) FROM imported_resources").fetchone()[0]
    packages = {}
    for name in ("chromadb", "sentence-transformers", "google-genai", "streamlit", "pytest"):
        try:
            packages[name] = version(name)
        except PackageNotFoundError:
            packages[name] = None
    result = {"created_at": datetime.now(timezone.utc).isoformat(), "documents": total,
              "empty_ementas": empty, "earliest_decision": earliest, "latest_decision": latest,
              "bodies": bodies, "imported_resources": resources, "python": platform.python_version(),
              "packages": packages, "quality_evaluation": "Não realizada; faltam julgamentos de relevância e revisão das sínteses."}
    try:
        from .search import collection
        coll = collection()
        result["index"] = {"collection": coll.name, "chunks": coll.count(), "parameters": coll.metadata}
    except Exception as exc:
        result["index"] = {"available": False, "error_type": type(exc).__name__}
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return result


def summarize_synthesis(path: Path) -> dict:
    """Agrega revisão por afirmação, sem confundir etiquetas com suporte."""
    import csv
    rows = list(csv.DictReader(path.open(encoding="utf-8-sig", newline="")))
    allowed = {"suportada", "parcial", "contradita", "sem_evidencia"}
    if not rows or any(row.get("status") not in allowed or not row.get("claim", "").strip() for row in rows):
        raise ValueError("Preencha claim e status: suportada, parcial, contradita ou sem_evidencia")
    if any(row["status"] == "suportada" and not row.get("evidence", "").strip() for row in rows):
        raise ValueError("Afirmações suportadas exigem trecho em evidence")
    counts = {status: sum(row["status"] == status for row in rows) for status in sorted(allowed)}
    return {"claims": len(rows), "counts": counts,
            "supported_rate": counts["suportada"] / len(rows), "source": str(path)}
