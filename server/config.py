"""Configuration centrale de Mobile Py IDE.

Toutes les valeurs peuvent être surchargées par variable d'environnement,
ce qui permet de lancer l'IDE depuis Termux sans toucher au code.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

APP_NAME = "Mobile Py IDE"
VERSION = "3.0.0"

MAX_FILE_BYTES = 5 * 1024 * 1024
MAX_UPLOAD_BYTES = 25 * 1024 * 1024
MAX_RESULTS = 200
MAX_RUN_SECONDS = int(os.environ.get("PYIDE_RUN_TIMEOUT", "30"))
MAX_OUTPUT_BYTES = 512 * 1024

# Emplacement où l'app Android embarque son Python (Chaquopy).
NATIVE = bool(os.environ.get("PYIDE_NATIVE"))


def _env_paths(name: str) -> list[Path]:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return []
    parts = [p for p in raw.replace(",", os.pathsep).split(os.pathsep) if p.strip()]
    return [Path(p).expanduser() for p in parts]


def _default_projects() -> Path:
    raw = os.environ.get("PYIDE_PROJECTS", "").strip()
    if raw:
        return Path(raw).expanduser()
    candidates = [
        Path.home() / "storage" / "shared" / "PyIDE",
        Path.home() / "PyIDE",
        Path.home() / "projects",
    ]
    for candidate in candidates:
        try:
            if candidate.parent.is_dir():
                return candidate
        except OSError:
            continue
    return Path.home() / "projects"


PROJECTS_ROOT = _default_projects()
try:
    PROJECTS_ROOT.mkdir(parents=True, exist_ok=True)
except OSError:
    PROJECTS_ROOT = Path.home()


def _place(path: Path, label: str, kind: str) -> dict | None:
    try:
        resolved = path.expanduser().resolve()
    except OSError:
        return None
    if not resolved.is_dir():
        return None
    return {
        "id": "",
        "label": label,
        "path": str(resolved),
        "kind": kind,
    }


def _build_places() -> list[dict]:
    """Dossiers accessibles depuis l'IDE (bac à sable multi-racines)."""
    entries: list[tuple[Path, str, str]] = [(PROJECTS_ROOT, "Projets", "projects")]
    entries.append((Path.home(), "Dossier personnel", "home"))

    # Stockage partagé Android (Termux : ~/storage/shared, app native : /sdcard).
    shared = [
        Path("/storage/emulated/0"),
        Path("/sdcard"),
        Path.home() / "storage" / "shared",
    ]
    for candidate in shared:
        if candidate.is_dir():
            entries.append((candidate, "Stockage du téléphone", "shared"))
            break

    for extra in _env_paths("PYIDE_ROOTS"):
        entries.append((extra, extra.name or str(extra), "extra"))

    places: list[dict] = []
    seen: set[str] = set()
    for path, label, kind in entries:
        place = _place(path, label, kind)
        if not place or place["path"] in seen:
            continue
        seen.add(place["path"])
        place["id"] = f"place{len(places)}"
        places.append(place)
    return places


PLACES = _build_places()
ROOTS = [Path(place["path"]) for place in PLACES]

# 127.0.0.1 par défaut : le serveur exécute du code arbitraire, il ne doit
# pas être exposé au réseau sans jeton.
HOST = os.environ.get("PYIDE_HOST", "127.0.0.1")
PORT = int(os.environ.get("PYIDE_PORT", "8765"))
TOKEN = os.environ.get("PYIDE_TOKEN", "").strip()

# Assistant IA optionnel : toute API compatible OpenAI
# (OpenAI, Ollama, LM Studio, llama.cpp server…).
AI_URL = os.environ.get("PYIDE_AI_URL", "").strip()
AI_KEY = os.environ.get("PYIDE_AI_KEY", "").strip()
AI_MODEL = os.environ.get("PYIDE_AI_MODEL", "").strip()
OLLAMA_URL = os.environ.get("PYIDE_OLLAMA_URL", "http://127.0.0.1:11434").rstrip("/")

# Gestionnaire de paquets : "pip" (serveur, Termux) ou "wheels" (app Android,
# installation de roues pures dans un dossier utilisateur).
PKG_BACKEND = os.environ.get(
    "PYIDE_PKG_BACKEND", "wheels" if NATIVE else "pip"
).strip() or "pip"
USER_SITE = Path(
    os.environ.get("PYIDE_USER_SITE", str(PROJECTS_ROOT.parent / ".pyide-packages"))
)
PYPI_JSON = os.environ.get("PYIDE_PYPI", "https://pypi.org/pypi").rstrip("/")

IS_ANDROID = "ANDROID_ROOT" in os.environ or "ANDROID_DATA" in os.environ or NATIVE
PYTHON_VERSION = sys.version.split()[0]
