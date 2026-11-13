"""Instala uma versão completa da base e do índice da release pública."""
import hashlib
import json
import os
import shutil
import tempfile
from pathlib import Path
from threading import Lock
from urllib.request import urlopen
from zipfile import ZipFile

BASE = "https://github.com/nadjaguerra/JurisIA/releases"
LOCK = Lock()


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
        if not (staging / "data/processed/jurisia.sqlite3").is_file() or not (
            staging / "vectorstore/chroma/active_index.json"
        ).is_file():
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
            with urlopen(f"{BASE}/latest/download/jurisia-manifest.json", timeout=30) as response:
                manifest = json.load(response)
            version = manifest["version"]
            if not version.isascii() or not version.isdecimal():
                raise ValueError("Versão inválida")
            target = home / version
            if not target.is_dir():
                with tempfile.TemporaryDirectory(dir=home) as tmp:
                    archive = Path(tmp) / "data.zip"
                    with urlopen(f"{BASE}/download/data-{version}/jurisia-data.zip", timeout=180) as source, archive.open("wb") as output:
                        shutil.copyfileobj(source, output)
                    target = install(home, manifest, archive)
        except Exception:
            if not pointer.is_file():
                raise
            target = home / pointer.read_text(encoding="ascii")
        os.environ["JURISIA_DATA_HOME"] = str(target)
