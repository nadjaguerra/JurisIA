"""Índice vetorial persistente, recuperação e reranking leve."""

import re
import sqlite3
import unicodedata
import json
import uuid
from functools import lru_cache

from .chunking import chunks
from .config import COLLECTION, DB, EMBEDDING_MODEL, VECTOR
from .prepare import get_documents


@lru_cache(maxsize=1)
def model():
    from sentence_transformers import SentenceTransformer
    return SentenceTransformer(EMBEDDING_MODEL)


@lru_cache(maxsize=1)
def _client():
    import chromadb
    VECTOR.mkdir(parents=True, exist_ok=True)
    return chromadb.PersistentClient(path=str(VECTOR))


@lru_cache(maxsize=2)
def _collection(name):
    return _client().get_collection(name)


def collection():
    pointer = VECTOR / "active_index.json"
    name = json.loads(pointer.read_text(encoding="utf-8"))["collection"] if pointer.exists() else COLLECTION
    return _collection(name)


@lru_cache(maxsize=64)
def _embedding(question):
    return model().encode([question], normalize_embeddings=True).tolist()


def index(limit: int = 2000, size: int = 70, overlap: int = 15,
          batch_size: int = 64) -> dict:
    chunks("", size, overlap)
    if limit < 0 or batch_size <= 0:
        raise ValueError("Use limit >= 0 e batch_size > 0")
    if not DB.exists():
        raise FileNotFoundError("Rode `jurisia prepare` primeiro.")
    import chromadb
    VECTOR.mkdir(parents=True, exist_ok=True)
    client = chromadb.PersistentClient(path=str(VECTOR))
    name = f"{COLLECTION}_{uuid.uuid4().hex}"
    coll = client.get_or_create_collection(
        name, metadata={"hnsw:space": "cosine", "embedding_model": EMBEDDING_MODEL,
                              "chunk_words": size, "overlap_words": overlap}
    )
    conn = sqlite3.connect(DB)
    cursor = conn.execute("""
      SELECT id, ementa, court_body, decision_date
      FROM documents WHERE LENGTH(TRIM(ementa)) > 0 ORDER BY id
    """)
    count = 0
    indexed = 0
    batch = []

    def flush():
        nonlocal indexed
        if not batch:
            return
        vectors = model().encode([item[1] for item in batch],
                                 batch_size=32, normalize_embeddings=True,
                                 show_progress_bar=False)
        coll.upsert(
            ids=[item[0] for item in batch],
            documents=[item[1] for item in batch],
            metadatas=[item[2] for item in batch],
            embeddings=vectors.tolist(),
        )
        indexed += len(batch)
        batch.clear()
        print(f"Chunks processados: {indexed}", flush=True)

    try:
        for ident, ementa, body, date in cursor:
            if limit and count >= limit:
                break
            count += 1
            for position, text in enumerate(chunks(ementa, size, overlap)):
                batch.append((f"{ident}:{position}", text, {
                    "document_id": ident, "position": position,
                    "court_body": body or "", "decision_date": int(date or 0),
                }))
                if len(batch) >= batch_size:
                    flush()
        flush()
    finally:
        conn.close()
    if not indexed:
        client.delete_collection(name)
        raise ValueError("Nenhuma ementa para indexar; índice anterior preservado.")
    pointer = VECTOR / "active_index.json"
    temporary = VECTOR / f"active_index_{uuid.uuid4().hex}.tmp"
    temporary.write_text(json.dumps({"collection": name, "model": EMBEDDING_MODEL,
                                    "size": size, "overlap": overlap,
                                    "documents": count, "chunks": indexed}), encoding="utf-8")
    temporary.replace(pointer)
    return {"documents_seen": count, "chunks_written": indexed,
            "total_chunks": coll.count()}


def _terms(value: str) -> set[str]:
    value = "".join(c for c in unicodedata.normalize("NFKD", value.lower())
                    if not unicodedata.combining(c))
    return set(re.findall(r"[a-z]{3,}", value)) - {
        "para", "por", "com", "uma", "qual", "quais", "sobre", "que", "stj",
        "entendimento", "jurisprudencia", "dos", "das",
    }


def lexical_search(question: str, k: int = 5, body: str | None = None,
                   year_from: int | None = None, year_to: int | None = None,
                   *, newest_first: bool = False, offset: int = 0) -> list[dict]:
    """Baseline de palavras com FTS5/BM25; sem embeddings nem geração."""
    if k <= 0 or offset < 0 or (year_from and year_to and year_from > year_to):
        raise ValueError("Confira a quantidade e o intervalo de anos.")
    terms = sorted(_terms(question))
    if not terms:
        return []
    from contextlib import closing
    with closing(sqlite3.connect(DB, timeout=60)) as db:
        if not db.execute("SELECT 1 FROM sqlite_master WHERE name='lexical_update'").fetchone():
            with db:
                db.execute("BEGIN IMMEDIATE")
                _prepare_lexical(db)
        filters = ["lexical_docs MATCH ?"]
        args = [' OR '.join('"' + term + '"' for term in terms)]
        for value, clause in ((body, "d.court_body = ?"),
                              (f"{year_from}0101" if year_from else None, "d.decision_date >= ?"),
                              (f"{year_to}1231" if year_to else None, "d.decision_date BETWEEN '00010101' AND ?")):
            if value is not None:
                filters.append(clause)
                args.append(value)
        join = " CROSS JOIN documents d ON d.id = lexical_docs.id" if newest_first or len(filters) > 1 else ""
        order = "d.decision_date DESC NULLS LAST, d.id" if newest_first else "rank"
        suffix = join + " WHERE " + " AND ".join(filters) + f" ORDER BY {order} LIMIT ? OFFSET ?"
        if newest_first:
            # Calcule trechos apenas para os documentos da página.
            ids = db.execute("SELECT lexical_docs.rowid FROM lexical_docs" + suffix, (*args, k, offset)).fetchall()
            rows = [db.execute(
                "SELECT id, snippet(lexical_docs,1,'','',' … ',40),rank FROM lexical_docs WHERE rowid=? AND lexical_docs MATCH ?",
                (rowid, args[0])).fetchone() for (rowid,) in ids]
            rows = [row for row in rows if row is not None]
        else:
            rows = db.execute(
                "SELECT lexical_docs.id, snippet(lexical_docs,1,'','',' … ',40),rank FROM lexical_docs"
                + suffix, (*args, k, offset)).fetchall()
    docs = get_documents([row[0] for row in rows])
    return [{"id": ident, "snippet": snippet, "lexical_score": -score,
             "document": docs[ident]} for ident, snippet, score in rows if ident in docs]


def _prepare_lexical(db):
    if db.execute("SELECT 1 FROM sqlite_master WHERE name='lexical_update'").fetchone():
        return
    exists = db.execute("SELECT 1 FROM sqlite_master WHERE name='lexical_docs'").fetchone()
    db.execute("CREATE VIRTUAL TABLE IF NOT EXISTS lexical_docs USING fts5(id UNINDEXED, ementa, tokenize='unicode61 remove_diacritics 2')")
    if not exists:
        db.execute("INSERT INTO lexical_docs SELECT id,ementa FROM documents")
    insert = "INSERT INTO lexical_docs(id,ementa) VALUES(new.id,new.ementa);"
    delete = "DELETE FROM lexical_docs WHERE id=old.id;"
    for operation, statement in (("insert", insert), ("delete", delete), ("update", delete + insert)):
        db.execute(f"CREATE TRIGGER IF NOT EXISTS lexical_{operation} AFTER {operation} ON documents BEGIN {statement} END")


def rerank(question: str, candidates: list[dict]) -> list[dict]:
    terms = _terms(question)
    for item in candidates:
        lexical = len(terms & _terms(item["snippet"])) / max(1, len(terms))
        item["ranking_score"] = round(0.85 * item["similarity"] + 0.15 * lexical, 4)
    return sorted(candidates, key=lambda d: d["ranking_score"], reverse=True)


def search(question: str, k: int = 5, body: str | None = None,
           year_from: int | None = None, year_to: int | None = None,
           min_similarity: float = 0.0, use_rerank: bool = True,
           *, newest_first: bool = False, offset: int = 0) -> list[dict]:
    if k <= 0 or offset < 0 or not -1 <= min_similarity <= 1:
        raise ValueError("Use k > 0 e similaridade entre -1 e 1")
    if year_from and year_to and year_from > year_to:
        raise ValueError("Ano inicial deve ser menor ou igual ao final")
    if not question.strip():
        return []
    coll = collection()
    count = coll.count()
    if not count:
        return []
    if coll.metadata and coll.metadata.get("embedding_model") != EMBEDDING_MODEL:
        raise RuntimeError("O modelo de embeddings mudou. Rode `jurisia index` novamente.")
    conditions = []
    if body:
        conditions.append({"court_body": body})
    if year_from:
        conditions.append({"decision_date": {"$gte": int(f"{year_from}0101")}})
    if year_to:
        conditions.append({"decision_date": {"$lte": int(f"{year_to}1231")}})
        if not year_from:
            conditions.append({"decision_date": {"$gt": 0}})
    where = ({"$and": conditions} if len(conditions) > 1 else
             conditions[0] if conditions else None)
    embedding = _embedding(question)
    results = coll.query(query_embeddings=embedding,
                         n_results=min(count, 600 if newest_first else max(k * 12, 40)),
                         where=where,
                         include=["documents", "metadatas", "distances"])
    candidates = []
    for text, meta, distance in zip(results["documents"][0],
                                     results["metadatas"][0],
                                     results["distances"][0]):
        similarity = max(-1.0, min(1.0, 1.0 - float(distance)))
        year = int(meta.get("decision_date") or 0) // 10000
        if similarity < min_similarity or (year_to and year > year_to):
            continue
        candidates.append({"id": meta["document_id"], "snippet": text,
                           "similarity": round(similarity, 4),
                           "_date": int(meta.get("decision_date") or 0),
                           "chunk_position": meta["position"]})
    ranked = rerank(question, candidates) if use_rerank else candidates
    chosen, seen = [], set()
    for candidate in ranked:
        if candidate["id"] not in seen:
            chosen.append(candidate)
            seen.add(candidate["id"])
        if not newest_first and len(chosen) >= k + offset:
            break
    if newest_first:
        chosen.sort(key=lambda hit: (-hit["_date"], hit["id"]))
    chosen = chosen[offset:offset + k]
    documents = get_documents([item["id"] for item in chosen])
    for item in chosen:
        item.pop("_date")
        item["document"] = documents.get(item["id"], {})
    return chosen
