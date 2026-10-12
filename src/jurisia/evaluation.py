"""Métricas de recuperação a partir de julgamentos humanos em CSV."""

import csv
import json
from pathlib import Path

from .search import search


def evaluate(path: Path, k: int = 5, mode: str = "rerank") -> dict:
    rows = list(csv.DictReader(path.open(encoding="utf-8-sig", newline="")))
    if not rows or not {"question", "relevant_ids"} <= set(rows[0]):
        raise ValueError("CSV exige colunas question,relevant_ids")
    recalls, precisions, reciprocal, hits, details = [], [], [], [], []
    for row in rows:
        relevant = {part.strip() for part in row["relevant_ids"].split("|")
                    if part.strip()}
        if not relevant:
            continue  # Sem resposta: avalie abstinência separadamente.
        retrieved = [item["id"] for item in search(
            row["question"], k=k, use_rerank=mode == "rerank")]
        matched = relevant.intersection(retrieved)
        precisions.append(len(matched) / k)
        recalls.append(len(matched) / len(relevant))
        hits.append(int(bool(matched)))
        reciprocal.append(next((1 / (i + 1) for i, ident in enumerate(retrieved)
                                if ident in relevant), 0))
        details.append({"question": row["question"], "expected": sorted(relevant),
                        "retrieved": retrieved, "hit": bool(matched)})
    if not details:
        raise ValueError("Inclua ao menos uma pergunta com ID relevante avaliado.")
    n = len(details)
    return {"n": n, "k": k, "precision_at_k": sum(precisions) / n,
            "recall_at_k": sum(recalls) / n, "mrr": sum(reciprocal) / n,
            "hit_rate": sum(hits) / n, "details": details}


def save(result: dict, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, ensure_ascii=False, indent=2),
                    encoding="utf-8")
