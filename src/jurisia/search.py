"""Índice vetorial persistente, recuperação e reranking leve."""

import re
import sqlite3
import unicodedata
from functools import lru_cache

from .chunking import chunks
from .config import COLLECTION, DB, EMBEDDING_MODEL, VECTOR
from .prepare import get_documents


@lru_cache(maxsize=1)
def model():
    from sentence_transformers import SentenceTransformer
    return SentenceTransformer(EMBEDDING_MODEL)


def collection():
    import chromadb
    VECTOR.mkdir(parents=True, exist_ok=True)
    client = chromadb.PersistentClient(path=str(VECTOR))
    return client.get_or_create_collection(
        COLLECTION, metadata={"hnsw:space": "cosine"}
    )


def index(limit: int = 2000, size: int = 70, overlap: int = 15,
          batch_size: int = 64) -> dict:
    if not DB.exists():
        raise FileNotFoundError("Rode `jurisia prepare` primeiro.")
    import chromadb
    VECTOR.mkdir(parents=True, exist_ok=True)
    client = chromadb.PersistentClient(path=str(VECTOR))
    try:
        client.delete_collection(COLLECTION)
    except Exception as exc:
        # Algumas versões lançam NotFoundError; não esconda outros problemas.
        if "not found" not in str(exc).lower() and "does not exist" not in str(exc).lower():
            raise
    coll = client.get_or_create_collection(
        COLLECTION, metadata={"hnsw:space": "cosine", "embedding_model": EMBEDDING_MODEL,
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
    conn.close()
    return {"documents_seen": count, "chunks_written": indexed,
            "total_chunks": coll.count()}


def _terms(value: str) -> set[str]:
    value = "".join(c for c in unicodedata.normalize("NFKD", value.lower())
                    if not unicodedata.combining(c))
    return set(re.findall(r"[a-z]{3,}", value)) - {
        "para", "por", "com", "uma", "qual", "quais", "sobre", "que", "stj",
        "entendimento", "jurisprudencia", "dos", "das",
    }


def rerank(question: str, candidates: list[dict]) -> list[dict]:
    terms = _terms(question)
    for item in candidates:
        lexical = len(terms & _terms(item["snippet"])) / max(1, len(terms))
        item["ranking_score"] = round(0.85 * item["similarity"] + 0.15 * lexical, 4)
    return sorted(candidates, key=lambda d: d["ranking_score"], reverse=True)


def search(question: str, k: int = 5, body: str | None = None,
           year_from: int | None = None, year_to: int | None = None,
           min_similarity: float = 0.0, use_rerank: bool = True) -> list[dict]:
    coll = collection()
    if not question.strip() or coll.count() == 0:
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
    where = ({"$and": conditions} if len(conditions) > 1 else
             conditions[0] if conditions else None)
    embedding = model().encode([question], normalize_embeddings=True).tolist()
    results = coll.query(query_embeddings=embedding,
                         n_results=min(coll.count(), max(k * 12, 40)),
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
                           "chunk_position": meta["position"]})
    ranked = rerank(question, candidates) if use_rerank else candidates
    chosen, seen = [], set()
    for candidate in ranked:
        if candidate["id"] not in seen:
            chosen.append(candidate)
            seen.add(candidate["id"])
        if len(chosen) >= k:
            break
    documents = get_documents([item["id"] for item in chosen])
    for item in chosen:
        item["document"] = documents.get(item["id"], {})
    return chosen
