"""Coleta recursos anunciados no catálogo CKAN oficial do STJ."""

import json
import re
import shutil
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode, urlparse
from urllib.request import Request, urlopen

from .config import RAW, STJ_DATASETS

CATALOG = "https://dadosabertos.web.stj.jus.br/api/3/action/package_show"
HEADERS = {"User-Agent": "JurisIA-academic-research/0.1"}
VALID_FILE = re.compile(r"^\d{8}\.(?:json|zip)$")


def _open(url: str, timeout: int = 60):
    return urlopen(Request(url, headers=HEADERS), timeout=timeout)


def catalog(slug: str) -> dict:
    url = CATALOG + "?" + urlencode({"id": slug})
    with _open(url, 30) as response:
        payload = json.load(response)
    if not payload.get("success"):
        raise RuntimeError(f"Catálogo não retornou sucesso: {slug}")
    return payload["result"]


def resources(slug: str) -> list[dict]:
    package = catalog(slug)
    rows = []
    for item in package["resources"]:
        name = item.get("name", "")
        url = item.get("url", "")
        parsed = urlparse(url)
        if not VALID_FILE.fullmatch(name) or parsed.scheme != "https":
            continue
        # Somente recursos hospedados pelo tribunal; nunca execute URLs arbitrárias.
        if parsed.hostname not in {"dadosabertos.web.stj.jus.br", "dadosabertos.stj.jus.br"}:
            raise ValueError(f"Verifique o domínio do recurso {name}: {parsed.hostname}")
        rows.append({"name": name, "url": url, "id": item["id"], "dataset": slug})
    return sorted(rows, key=lambda r: r["name"])


def _download(item: dict, path: Path) -> None:
    tmp = path.with_suffix(path.suffix + ".part")
    for attempt in range(3):
        try:
            with _open(item["url"], 90) as response, tmp.open("wb") as out:
                shutil.copyfileobj(response, out, length=1024 * 1024)
            if not tmp.stat().st_size:
                raise ValueError("Arquivo vazio")
            if path.suffix == ".json":
                with tmp.open(encoding="utf-8-sig") as f:
                    if not isinstance(json.load(f), list):
                        raise ValueError("JSON não é uma lista")
            else:
                from zipfile import ZipFile
                with ZipFile(tmp) as z:
                    if z.testzip() is not None:
                        raise ValueError("ZIP corrompido")
            tmp.replace(path)
            return
        except Exception:
            tmp.unlink(missing_ok=True)
            if attempt == 2:
                raise
            time.sleep(2 ** attempt)


def sync(slugs: list[str] | None = None) -> dict[str, int]:
    slugs = slugs or STJ_DATASETS
    RAW.mkdir(parents=True, exist_ok=True)
    summary = {}
    for slug in slugs:
        folder = RAW / slug
        folder.mkdir(exist_ok=True)
        items = resources(slug)
        # Um arquivo local previamente baixado da Terceira Turma pode ser reutilizado.
        for item in items:
            target = folder / item["name"]
            legacy = RAW / item["name"] if slug == "espelhos-de-acordaos-terceira-turma" else None
            if not target.exists() and legacy and legacy.exists():
                shutil.copy2(legacy, target)
            if not target.exists():
                print(f"Baixando {slug}/{item['name']}", flush=True)
                _download(item, target)
        manifest = {
            "dataset": slug,
            "collected_at_utc": datetime.now(timezone.utc).isoformat(),
            "dataset_url": f"https://dadosabertos.web.stj.jus.br/dataset/{slug}",
            "resources": items,
        }
        (folder / "manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        summary[slug] = len(items)
    return summary
