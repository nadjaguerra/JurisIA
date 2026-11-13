"""Resumos dos documentos retornados e comparação de rankings."""
from collections import Counter


def group(hit, field):
    value = hit["document"].get(field)
    if field == "decision_date" and value:
        value = str(value)[:4]
    return value or "Não informado"


def distribution(hits, field):
    return Counter(group(hit, field) for hit in hits)


def rank_comparison(lexical, semantic):
    def positions(hits):
        return {hit["id"]: (rank, hit["document"]) for rank, hit in enumerate(hits, 1)}
    left, right = positions(lexical), positions(semantic)
    rows = []
    for ident in dict.fromkeys([*left, *right]):
        a, b = left.get(ident), right.get(ident)
        doc = (a or b)[1]
        rows.append({"ID": ident, "Processo": " ".join(filter(None, [doc.get("process_class"), doc.get("process_number")])),
                     "Palavras": a[0] if a else None, "Significado": b[0] if b else None,
                     "Presença": "Nas duas" if a and b else "Só palavras" if a else "Só significado"})
    return rows
