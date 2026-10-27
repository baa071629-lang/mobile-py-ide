"""Configuration centrale de Mobile Py IDE.

Toutes les valeurs peuvent être surchargées par variable d'environnement,
ce qui permet de lancer l'IDE depuis Termux sans toucher au code.
"""

from __future__ import annotations

import os
from pathlib import Path

APP_NAME = "Mobile Py IDE"
VERSION = "2.0.0"

MAX_FILE_BYTES = 5 * 1024 * 1024
MAX_UPLOAD_BYTES = 25 * 1024 * 1024
MAX_RESULTS = 200
MAX_RUN_SECONDS = int(os.environ.get("PYIDE_RUN_TIMEOUT", "30"))
MAX_OUTPUT_BYTES = 512 * 1024


def _projects_root() -> Path:
    raw = os.environ.get("PYIDE_PROJECTS", "").strip()
    if not raw:
        shared = Path.home() / "storage" / "shared" / "PydroidProjects"
        raw = str(shared if shared.is_dir() else Path.home() / "projects")
    root = Path(raw).expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    return root


PROJECTS_ROOT = _projects_root()

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
