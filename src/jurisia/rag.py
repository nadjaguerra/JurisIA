"""Busca e síntese fundamentada nas ementas recuperadas do STJ."""

import os
import re
import sqlite3
import time

from .config import DB, GEMINI_MODEL
from .prepare import connect
from .search import search, lexical_search

SYSTEM = """Você é um assistente acadêmico de pesquisa jurisprudencial do STJ.
Use SOMENTE os documentos numerados no CONTEXTO. Não use conhecimento externo.
Não invente acórdãos, processos, datas, relatores, órgãos ou conclusões.
Cada afirmação jurídica precisa terminar com uma referência [D1], [D2] etc.
Não cite documento que não esteja no contexto. Se não houver evidência suficiente,
retorne somente EVIDENCIA_INSUFICIENTE.
Distinga decisão de mérito de decisão limitada por óbices processuais.
Responda em português claro, com vários parágrafos curtos separados por uma linha
em branco. Comece pela resposta principal e depois explique os fundamentos.
Quando as fontes permitirem, inclua um exemplo hipotético curto, identificado
como Exemplo ilustrativo e fundamentado nas fontes. Não prometa resultados.
Organize por aspectos apenas quando as fontes sustentarem cada aspecto.
Não apresente aconselhamento jurídico. Seja sucinto e preciso.
"""

CONTEXT_EMENTA_CHARS = 2200


def context(items: list[dict], max_chars: int = CONTEXT_EMENTA_CHARS) -> str:
    parts = []
    for number, item in enumerate(items, start=1):
        doc = item["document"]
        parts.append(
            f"[D{number}] ID={doc.get('id')} | processo="
            f"{doc.get('process_class')} {doc.get('process_number')} | "
            f"órgão={doc.get('court_body')} | relator={doc.get('rapporteur')} | "
            f"julgamento={doc.get('decision_date')}\n"
            f"EMENTA: {(doc.get('ementa') or '')[:max_chars]}\n"
            f"TRECHO RECUPERADO: {item['snippet']}"
        )
    return "\n\n".join(parts)


def _generate_with_retry(client, contents, attempts=3):
    """Repete somente falhas transitórias do serviço; preserva o erro final."""
    for attempt in range(attempts):
        try:
            return client.models.generate_content(
                model=GEMINI_MODEL,
                contents=contents,
            )
        except Exception as exc:
            code = str(getattr(exc, "code", ""))
            message = str(exc)
            transient = code in {"500", "502", "503", "504"} or bool(
                re.match(r"^(500|502|503|504)\b", message)
            )
            if not transient or attempt == attempts - 1:
                raise
            time.sleep(2 ** (attempt + 1))


def generate(question: str, items: list[dict]) -> str:
    if not items:
        return "Não encontrei evidência suficiente na base indexada para responder."
    key = os.getenv("GEMINI_API_KEY")
    if not key:
        raise RuntimeError("Defina GEMINI_API_KEY no arquivo .env para gerar respostas.")
    from google import genai

    client = genai.Client(api_key=key)
    response = _generate_with_retry(
        client,
        f"{SYSTEM}\n\nPERGUNTA: {question}\n\nCONTEXTO:\n{context(items)}",
    )
    answer = (response.text or "").strip()
    if answer == "EVIDENCIA_INSUFICIENTE":
        return "Os trechos recuperados não oferecem evidência suficiente para responder à pergunta."
    if not answer:
        return "O modelo não retornou uma resposta. Consulte os documentos recuperados."
    allowed = {f"D{i}" for i in range(1, len(items) + 1)}
    cited = set(re.findall(r"\[D(\d+)\]", answer))
    if not cited or any(f"D{number}" not in allowed for number in cited):
        return (
            "Não foi possível validar as referências na resposta gerada. "
            "Consulte os documentos recuperados."
        )
    return answer


def retrieve(question: str, k: int = 5, body: str | None = None,
             year_from: int | None = None, year_to: int | None = None,
             min_similarity: float = 0.30, use_rerank: bool = True,
             method: str = "semantic", *, newest_first: bool = False,
             offset: int = 0) -> list[dict]:
    if method not in {"lexical", "semantic"}:
        raise ValueError("Método de busca desconhecido.")
    filters = dict(k=k, body=body, year_from=year_from, year_to=year_to)
    if newest_first or offset:
        filters.update(newest_first=newest_first, offset=offset)
    return (lexical_search(question, **filters) if method == "lexical" else
            search(question, **filters, min_similarity=min_similarity, use_rerank=use_rerank))


def ask(question: str, k: int = 5, body: str | None = None,
        year_from: int | None = None, year_to: int | None = None,
        min_similarity: float = 0.30, use_rerank: bool = True,
        with_gemini: bool = True, method: str = "semantic",
        *, newest_first: bool = False) -> dict:
    started = time.monotonic()
    hits = retrieve(question, k, body, year_from, year_to, min_similarity,
                    use_rerank, method, newest_first=newest_first)
    search_seconds = time.monotonic() - started
    answer = generate(question, hits) if with_gemini else ""
    elapsed = time.monotonic() - started
    db = connect(DB)
    with db:
        question_id = db.execute(
            "INSERT INTO questions(question,response_seconds,retrieved,mode,search_seconds,synthesis_seconds) VALUES (?,?,?,?,?,?)",
            (question, elapsed, len(hits), "rag" if with_gemini else "retrieval",
             search_seconds, elapsed - search_seconds if with_gemini else None),
        ).lastrowid
    db.close()
    return {"answer": answer, "hits": hits, "seconds": elapsed,
            "question_id": question_id}


def record_synthesis(question_id: int, seconds: float) -> None:
    db = connect(DB)
    with db:
        db.execute("UPDATE questions SET synthesis_seconds=?, response_seconds=COALESCE(search_seconds,response_seconds)+?,mode='rag' WHERE id=?",
                   (seconds, seconds, question_id))
    db.close()


def record_result_feedback(question_id: int, document_id: str, rank: int,
                           method: str, relevant: bool) -> None:
    from contextlib import closing
    with closing(connect(DB)) as db, db:
        db.execute("""
          INSERT INTO result_feedback VALUES (?,?,?,?,?)
          ON CONFLICT(question_id, document_id) DO UPDATE SET relevant=excluded.relevant
        """, (question_id, document_id, rank, method, int(relevant)))


def record_feedback(question_id: int, useful: bool | None,
                    clarity: int | None, relevance: int | None,
                    confidence: int | None, usability: int | None,
                    satisfaction: int | None, reuse: str,
                    comment: str = "") -> None:
    db = connect(DB)
    with db:
        db.execute("""
            INSERT INTO feedback(question_id,useful,clarity,relevance,confidence,
                                 usability,satisfaction,reuse,comment)
            VALUES (?,?,?,?,?,?,?,?,?)
        """, (question_id, None if useful is None else int(useful),
              clarity, relevance, confidence, usability, satisfaction,
              reuse, comment[:2000]))
    db.close()


def metrics() -> dict:
    if not DB.exists():
        return {"documents": 0, "questions": 0, "avg_seconds": 0,
                "avg_retrieved": 0, "feedback": 0, "useful_rate": None}
    db = connect(DB)
    documents = db.execute("SELECT COUNT(*) FROM documents").fetchone()[0]
    q, seconds, retrieved = db.execute("""
        SELECT COUNT(*), AVG(response_seconds), AVG(retrieved) FROM questions
    """).fetchone()
    f, useful = db.execute("SELECT COUNT(*), AVG(useful) FROM feedback").fetchone()
    search_seconds, synthesis_seconds = db.execute(
        "SELECT AVG(search_seconds),AVG(synthesis_seconds) FROM questions").fetchone()
    db.close()
    return {"documents": documents, "questions": q,
            "avg_seconds": seconds or 0, "avg_retrieved": retrieved or 0,
            "feedback": f, "useful_rate": useful,
            "avg_search_seconds": search_seconds or 0,
            "avg_synthesis_seconds": synthesis_seconds or 0}
