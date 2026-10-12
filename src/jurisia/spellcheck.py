"""Correção conservadora de consultas usando o vocabulário das ementas."""

import gzip
import json
import os
import re
import sqlite3
import unicodedata
from collections import Counter
from functools import lru_cache
from pathlib import Path

from .config import DB

WORDS = re.compile(r"[^\W\d_]+", re.UNICODE)
LETTERS = "abcdefghijklmnopqrstuvwxyz"


def normalize(word):
    return "".join(
        char
        for char in unicodedata.normalize("NFKD", word.lower())
        if not unicodedata.combining(char)
    )


@lru_cache(maxsize=1)
def _vocabulary(path, count, last_row, text_size):
    cache = Path(path).parent / "spellcheck_vocabulary.json.gz"
    signature = [path, count, last_row, text_size]

    try:
        with gzip.open(cache, "rt", encoding="utf-8") as stream:
            data = json.load(stream)

        if data["signature"] == signature:
            return data["frequencies"], data["surfaces"]
    except (OSError, ValueError, KeyError, EOFError):
        pass

    frequencies = Counter()
    variants = Counter()

    with sqlite3.connect(path) as conn:
        for (text,) in conn.execute(
            "SELECT ementa FROM documents WHERE ementa IS NOT NULL"
        ):
            for word in WORDS.findall(text.lower()):
                key = normalize(word)

                if len(key) >= 3:
                    frequencies[key] += 1
                    variants[(key, word)] += 1

    surfaces = {}

    for (key, word), frequency in variants.most_common():
        surfaces.setdefault(key, word)

    data = {
        "signature": signature,
        "frequencies": dict(frequencies),
        "surfaces": surfaces,
    }

    # Reutiliza o vocabulário nas próximas inicializações.
    temporary = cache.with_name(
        cache.name + f".{os.getpid()}.tmp"
    )

    try:
        with gzip.open(temporary, "wt", encoding="utf-8") as stream:
            json.dump(data, stream, ensure_ascii=False)

        os.replace(temporary, cache)
    except OSError:
        pass
    finally:
        temporary.unlink(missing_ok=True)

    return data["frequencies"], surfaces


def _edits(word):
    splits = [
        (word[:index], word[index:])
        for index in range(len(word) + 1)
    ]

    deletions = {
        left + right[1:]
        for left, right in splits
        if right
    }

    transpositions = {
        left + right[1] + right[0] + right[2:]
        for left, right in splits
        if len(right) > 1
    }

    replacements = {
        left + letter + right[1:]
        for left, right in splits
        if right
        for letter in LETTERS
    }

    insertions = {
        left + letter + right
        for left, right in splits
        for letter in LETTERS
    }

    return deletions | transpositions | replacements | insertions


def _context_counts(anchor):
    pairs = Counter()

    if not anchor or len(anchor) < 4:
        return pairs

    with sqlite3.connect(DB) as conn:
        rows = conn.execute(
            "SELECT ementa FROM documents WHERE ementa LIKE ? LIMIT 300",
            ("%" + anchor + "%",),
        )

        for (text,) in rows:
            words = [
                normalize(word)
                for word in WORDS.findall(text)
            ]
            pairs.update(zip(words, words[1:]))

    return pairs


def correct_query(question):
    """Retorna a consulta corrigida e uma sugestão quando houver dúvida."""
    result = {
        "original": question,
        "query": question,
        "suggestion": "",
        "changes": [],
    }

    if not DB.exists():
        return result

    # Consultas registradas não invalidam o vocabulário das ementas.
    with sqlite3.connect(DB) as conn:
        signature = conn.execute(
            """
            SELECT COUNT(*),
                   COALESCE(MAX(rowid), 0),
                   COALESCE(SUM(LENGTH(ementa)), 0)
            FROM documents
            """
        ).fetchone()

    frequencies, surfaces = _vocabulary(
        str(DB.resolve()),
        *signature,
    )

    matches = list(WORDS.finditer(question))
    replacements = []
    suggestions = []

    for index, match in enumerate(matches):
        word = match.group()
        key = normalize(word)

        before = (
            question[match.start() - 1:match.start()]
            if match.start()
            else ""
        )
        after = question[match.end():match.end() + 1]

        if (
            len(key) < 5
            or len(key) > 30
            or key in frequencies
            or (word.isupper() and len(word) <= 5)
            or (index > 0 and word.istitle())
            or before.isdigit()
            or after.isdigit()
            or before == "/"
            or after == "/"
        ):
            continue

        candidates = [
            candidate
            for candidate in _edits(key)
            if frequencies.get(candidate, 0) >= 3
        ]

        if not candidates:
            continue

        previous = (
            normalize(matches[index - 1].group())
            if index
            else ""
        )
        following = (
            normalize(matches[index + 1].group())
            if index + 1 < len(matches)
            else ""
        )

        anchor = (
            matches[index - 1].group()
            if index
            else (
                matches[index + 1].group()
                if index + 1 < len(matches)
                else ""
            )
        )

        pairs = _context_counts(anchor)

        def context(candidate):
            return (
                pairs[(previous, candidate)]
                + pairs[(candidate, following)]
            )

        candidates.sort(
            key=lambda candidate: (
                context(candidate),
                frequencies[candidate],
                candidate,
            ),
            reverse=True,
        )

        best = candidates[0]
        runner = candidates[1] if len(candidates) > 1 else None

        confident = (
            runner is None
            or (
                context(best) >= 2
                and context(best) >= 3 * max(1, context(runner))
            )
        )

        replacement = surfaces[best]

        if word[0].isupper():
            replacement = replacement.capitalize()

        entry = (
            match.start(),
            match.end(),
            replacement,
        )

        if confident:
            replacements.append(entry)
            result["changes"].append(
                {
                    "original": word,
                    "corrected": replacement,
                }
            )
        else:
            suggestions.append(entry)

    def apply(entries):
        text = question

        for start, end, replacement in sorted(entries, reverse=True):
            text = text[:start] + replacement + text[end:]

        return text

    result["query"] = apply(replacements)

    if suggestions:
        result["suggestion"] = apply(replacements + suggestions)

    return result