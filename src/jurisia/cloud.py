"""Instala uma versão completa da base e do índice da release pública."""
import hashlib
import json
import logging
import os
import shutil
import tempfile
from pathlib import Path
from threading import Lock
from urllib.request import Request, urlopen
from urllib.error import URLError
from zipfile import ZipFile

BASE = "https://github.com/nadjaguerra/JurisIA/releases"
API = "https://api.github.com/repos/nadjaguerra/JurisIA/releases"
LOCK = Lock()
LOG = logging.getLogger(__name__)
FIRST_LEXICAL_TAG = "lexical-435294001061"


def open_url(url, timeout):
    return urlopen(Request(url, headers={"User-Agent": "JurisIA-Cloud/1.0"}), timeout=timeout)


def latest_manifest():
    try:
        with open_url(f"{BASE}/latest/download/jurisia-manifest.json", timeout=30) as response:
            return json.load(response)
    except URLError:
        pass
    try:
        with open_url(f"{API}?per_page=30", timeout=30) as response:
            releases = json.load(response)
    except URLError:
        releases = []
    releases.append({"tag_name": FIRST_LEXICAL_TAG})
    for release in releases:
        tag = release["tag_name"]
        if tag.startswith("lexical-") and tag.removeprefix("lexical-").isascii() and tag.removeprefix("lexical-").isdecimal():
            with open_url(f"{BASE}/download/{tag}/jurisia-manifest.json", timeout=30) as response:
                manifest = json.load(response)
            if manifest.get("lexical_only") is True and tag == f"lexical-{manifest['version']}":
                return manifest
    raise FileNotFoundError("Nenhuma base pública disponível")


def install(home, manifest, archive):
    version = manifest["version"]
    if not version.isascii() or not version.isdecimal():
        raise ValueError("Versão inválida")
    with archive.open("rb") as file:
        if hashlib.file_digest(file, "sha256").hexdigest() != manifest["sha256"]:
            raise ValueError("Checksum incorreto")
    target = home / version
    with tempfile.TemporaryDirectory(dir=home) as temporary:
        staging = Path(temporary) / "snapshot"
        with ZipFile(archive) as zipped:
            for name in zipped.namelist():
                if name != "data/processed/jurisia.sqlite3" and not name.startswith("vectorstore/chroma/"):
                    raise ValueError("Arquivo inesperado no snapshot")
                if any(part in {"..", "."} or ":" in part or "\\" in part for part in name.split("/")):
                    raise ValueError("Caminho inválido")
            zipped.extractall(staging)
        if not (staging / "data/processed/jurisia.sqlite3").is_file() or (not manifest.get("lexical_only") and not (
            staging / "vectorstore/chroma/active_index.json"
        ).is_file()):
            raise ValueError("Snapshot incompleto")
        staging.replace(target)
    pointer = home / "current.tmp"
    pointer.write_text(version, encoding="ascii")
    pointer.replace(home / "current")
    return target


def setup_cloud():
    if os.getenv("JURISIA_CLOUD") != "1" or os.getenv("JURISIA_DATA_HOME"):
        return
    with LOCK:
        if os.getenv("JURISIA_DATA_HOME"):
            return
        home = Path(tempfile.gettempdir()) / "jurisia-cloud"
        home.mkdir(exist_ok=True)
        pointer = home / "current"
        try:
            manifest = latest_manifest()
            version = manifest["version"]
            if not version.isascii() or not version.isdecimal():
                raise ValueError("Versão inválida")
            target = home / version
            if not target.is_dir():
                with tempfile.TemporaryDirectory(dir=home) as tmp:
                    archive = Path(tmp) / "data.zip"
                    prefix = "lexical" if manifest.get("lexical_only") else "data"
                    with open_url(f"{BASE}/download/{prefix}-{version}/jurisia-data.zip", timeout=180) as source, archive.open("wb") as output:
                        shutil.copyfileobj(source, output)
                    target = install(home, manifest, archive)
        except Exception:
            LOG.exception("Falha ao carregar a base pública do JurisIA")
            if not pointer.is_file():
                raise
            target = home / pointer.read_text(encoding="ascii")
        os.environ["JURISIA_DATA_HOME"] = str(target)
