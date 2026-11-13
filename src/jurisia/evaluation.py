"""Métricas de recuperação a partir de julgamentos humanos em CSV."""

import csv
import json
import time
import platform
from datetime import datetime, timezone
from pathlib import Path

from .search import search, lexical_search


def evaluate(path: Path, k: int = 5, mode: str = "rerank", min_similarity: float = 0.30) -> dict:
    if k <= 0 or mode not in {"vector", "rerank", "lexical"}:
        raise ValueError("Use k > 0 e mode vector, rerank ou lexical")
    rows = list(csv.DictReader(path.open(encoding="utf-8-sig", newline="")))
    if not rows or not {"question", "relevant_ids"} <= set(rows[0]):
        raise ValueError("CSV exige colunas question,relevant_ids")
    recalls, precisions, reciprocal, hits, details = [], [], [], [], []
    unanswered, abstentions, timings = 0, 0, []
    for row in rows:
        if not row["question"].strip():
            continue
        relevant = {part.strip() for part in row["relevant_ids"].split("|")
                    if part.strip()}
        no_answer = row.get("category", "").strip() == "sem_resposta"
        if not relevant and not no_answer:
            continue
        started = time.monotonic()
        found = (lexical_search(row["question"], k=k) if mode == "lexical" else search(
            row["question"], k=k, use_rerank=mode == "rerank", min_similarity=min_similarity))
        seconds = time.monotonic() - started
        timings.append(seconds)
        retrieved = [item["id"] for item in found]
        if no_answer:
            unanswered += 1
            abstentions += int(not retrieved)
            details.append({"question": row["question"], "category": "sem_resposta",
                            "retrieved": retrieved, "abstained": not retrieved, "seconds": seconds})
            continue
        matched = relevant.intersection(retrieved)
        precisions.append(len(matched) / k)
        recalls.append(len(matched) / len(relevant))
        hits.append(int(bool(matched)))
        reciprocal.append(next((1 / (i + 1) for i, ident in enumerate(retrieved)
                                if ident in relevant), 0))
        details.append({"question": row["question"], "expected": sorted(relevant),
                        "retrieved": retrieved, "hit": bool(matched), "seconds": seconds})
    if not details:
        raise ValueError("Inclua ao menos uma pergunta com ID relevante avaliado.")
    n = len(precisions)
    return {"n": n, "k": k, "mode": mode, "min_similarity": min_similarity,
            "created_at": datetime.now(timezone.utc).isoformat(), "python": platform.python_version(),
            "precision_at_k": sum(precisions) / n if n else None,
            "recall_at_k": sum(recalls) / n if n else None,
            "mrr": sum(reciprocal) / n if n else None,
            "hit_rate": sum(hits) / n if n else None,
            "unanswerable_n": unanswered,
            "correct_abstentions": abstentions, "false_evidence": unanswered - abstentions,
            "abstention_rate": abstentions / unanswered if unanswered else None,
            "avg_seconds": sum(timings) / len(timings),
            "abstention_scope": "recuperação; não avalia abstinência textual do Gemini",
            "details": details}


def save(result: dict, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, ensure_ascii=False, indent=2),
                    encoding="utf-8")
