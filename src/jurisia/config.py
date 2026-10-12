import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env")
RAW = ROOT / "data" / "raw"
PROCESSED = ROOT / "data" / "processed"
DB = PROCESSED / "jurisia.sqlite3"
VECTOR = ROOT / "vectorstore" / "chroma"
COLLECTION = "ementas_stj_v1"
EMBEDDING_MODEL = os.getenv(
    "EMBEDDING_MODEL", "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
)
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")

STJ_DATASETS = [
    f"espelhos-de-acordaos-{name}-turma"
    for name in ("primeira", "segunda", "terceira", "quarta", "quinta", "sexta")
] + [
    "espelhos-de-acordaos-primeira-secao",
    "espelhos-de-acordaos-segunda-secao",
    "espelhos-de-acordaos-terceira-secao",
    "espelhos-de-acordaos-corte-especial",
]
