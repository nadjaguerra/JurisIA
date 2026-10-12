"""Fragmentação conservadora das ementas com sobreposição de palavras."""

import re


def chunks(text: str, size: int = 180, overlap: int = 30) -> list[str]:
    if size <= 0 or overlap < 0 or overlap >= size:
        raise ValueError("Use size > overlap >= 0")
    words = re.findall(r"\S+", re.sub(r"\s+", " ", text.strip()))
    if not words:
        return []
    result = []
    step = size - overlap
    for start in range(0, len(words), step):
        result.append(" ".join(words[start:start + size]))
        if start + size >= len(words):
            break
    return result
