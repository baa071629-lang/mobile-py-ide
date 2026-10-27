"""Opérations fichiers sécurisées, confinées au dossier projets."""

from __future__ import annotations

import os
import shutil
import time
import uuid
from pathlib import Path

from .config import MAX_FILE_BYTES, MAX_RESULTS, MAX_UPLOAD_BYTES, PROJECTS_ROOT

SKIP_DIRS = {
    ".git", ".hg", ".svn", ".venv", "venv", "env", "__pycache__",
    "node_modules", ".mypy_cache", ".pytest_cache", ".ruff_cache",
    ".idea", ".vscode", ".pyide-trash",
}
TEXT_SEARCH_LIMIT = 1 * 1024 * 1024


class ApiError(Exception):
    def __init__(self, status_code: int, detail: str):
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


def _within(path: Path) -> bool:
    return path == PROJECTS_ROOT or PROJECTS_ROOT in path.parents


def safe_path(value: str | None) -> Path:
    """Résout un chemin relatif (ou absolu) sans jamais sortir des projets."""
    value = (value or "").strip()
    if "\x00" in value:
        raise ApiError(400, "Chemin invalide")
    raw = Path(value) if value else PROJECTS_ROOT
    if not raw.is_absolute():
        raw = PROJECTS_ROOT / raw
    try:
        resolved = raw.resolve()
    except (OSError, RuntimeError):
        raise ApiError(400, "Chemin invalide")
    if not _within(resolved):
        raise ApiError(403, "Chemin hors du dossier projets")
    return resolved


def relpath(path: Path) -> str:
    if path == PROJECTS_ROOT:
        return ""
    return path.relative_to(PROJECTS_ROOT).as_posix()


def _validate_name(name: str) -> str:
    name = name.strip()
    if not name or name in {".", ".."} or "/" in name or "\\" in name or "\x00" in name:
        raise ApiError(400, "Nom de fichier invalide")
    return name


def _is_temp(path: Path) -> bool:
    return path.name.startswith(".pyide-")


def _entry(path: Path) -> dict:
    try:
        stat = path.stat()
    except OSError:
        stat = None
    return {
        "name": path.name,
        "isDir": path.is_dir(),
        "rel": relpath(path),
        "size": stat.st_size if stat and path.is_file() else 0,
        "mtime": int(stat.st_mtime * 1000) if stat else 0,
    }


def list_dir(dir_rel: str = "", show_hidden: bool = False) -> dict:
    target = safe_path(dir_rel)
    if not target.is_dir():
        raise ApiError(404, "Dossier introuvable")

    entries: list[dict] = []
    for entry in target.iterdir():
        if not show_hidden and entry.name.startswith("."):
            continue
        if _is_temp(entry):
            continue
        try:
            if entry.is_symlink() and not _within(entry.resolve()):
                continue
        except OSError:
            continue
        entries.append(_entry(entry))
    entries.sort(key=lambda e: (not e["isDir"], e["name"].lower()))

    parent = None if target == PROJECTS_ROOT else relpath(target.parent)
    return {
        "root": str(PROJECTS_ROOT),
        "parent": parent,
        "dir": relpath(target),
        "entries": entries,
    }


def read_file(path: str) -> dict:
    target = safe_path(path)
    if not target.is_file():
        raise ApiError(404, "Fichier introuvable")
    try:
        size = target.stat().st_size
    except OSError as exc:
        raise ApiError(500, f"Lecture impossible : {exc}") from exc
    if size > MAX_FILE_BYTES:
        raise ApiError(413, "Fichier trop volumineux (max 5 Mo)")
    try:
        content = target.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise ApiError(415, "Fichier non UTF-8 : ouverture impossible") from exc
    except OSError as exc:
        raise ApiError(500, f"Lecture impossible : {exc}") from exc
    return {
        "path": relpath(target),
        "content": content,
        "size": size,
        "mtime": int(target.stat().st_mtime * 1000),
    }


def _atomic_write(target: Path, content: str) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_name(f".pyide-tmp-{uuid.uuid4().hex[:12]}")
    try:
        tmp.write_text(content, encoding="utf-8", newline="")
        os.replace(tmp, target)
    except OSError as exc:
        raise ApiError(500, f"Écriture impossible : {exc}") from exc
    finally:
        if tmp.exists():
            try:
                tmp.unlink()
            except OSError:
                pass


def save_file(path: str, content: str) -> dict:
    if len(content.encode("utf-8")) > MAX_FILE_BYTES:
        raise ApiError(413, "Contenu trop volumineux (max 5 Mo)")
    target = safe_path(path)
    if target == PROJECTS_ROOT or target.is_dir():
        raise ApiError(400, "Le chemin désigne un dossier")
    _atomic_write(target, content)
    stat = target.stat()
    return {"ok": True, "path": relpath(target), "size": stat.st_size,
            "mtime": int(stat.st_mtime * 1000)}


def make_dir(path: str) -> dict:
    target = safe_path(path)
    if target == PROJECTS_ROOT:
        raise ApiError(400, "Dossier déjà existant")
    if target.exists():
        raise ApiError(409, "Ce chemin existe déjà")
    try:
        target.mkdir(parents=True)
    except OSError as exc:
        raise ApiError(500, f"Création impossible : {exc}") from exc
    return {"ok": True, "path": relpath(target)}


def rename_path(path: str, new_path: str) -> dict:
    source = safe_path(path)
    if source == PROJECTS_ROOT:
        raise ApiError(400, "Impossible de renommer la racine")
    if not source.exists():
        raise ApiError(404, "Chemin introuvable")
    destination = safe_path(new_path)
    _validate_name(destination.name)
    if destination == source:
        return {"ok": True, "path": relpath(source)}
    if destination.exists():
        raise ApiError(409, "La destination existe déjà")
    try:
        destination.parent.mkdir(parents=True, exist_ok=True)
        source.rename(destination)
    except OSError as exc:
        raise ApiError(500, f"Renommage impossible : {exc}") from exc
    return {"ok": True, "path": relpath(destination)}


def delete_path(path: str) -> dict:
    target = safe_path(path)
    if target == PROJECTS_ROOT:
        raise ApiError(400, "Impossible de supprimer la racine")
    if not target.exists() and not target.is_symlink():
        raise ApiError(404, "Chemin introuvable")
    try:
        if target.is_dir() and not target.is_symlink():
            shutil.rmtree(target)
        else:
            target.unlink()
    except OSError as exc:
        raise ApiError(500, f"Suppression impossible : {exc}") from exc
    return {"ok": True}


def unique_name(directory: Path, filename: str) -> str:
    filename = _validate_name(filename)
    candidate = directory / filename
    if not candidate.exists():
        return filename
    stem, suffix = candidate.stem, candidate.suffix
    for index in range(1, 1000):
        candidate = directory / f"{stem} ({index}){suffix}"
        if not candidate.exists():
            return candidate.name
    raise ApiError(409, "Trop de fichiers portant le même nom")


def upload_file(dir_rel: str, filename: str, data: bytes) -> dict:
    if len(data) > MAX_UPLOAD_BYTES:
        raise ApiError(413, "Fichier trop volumineux (max 25 Mo)")
    target_dir = safe_path(dir_rel)
    if not target_dir.is_dir():
        raise ApiError(404, "Dossier de destination introuvable")
    name = unique_name(target_dir, Path(filename).name or "fichier")
    target = target_dir / name
    try:
        target.write_bytes(data)
    except OSError as exc:
        raise ApiError(500, f"Envoi impossible : {exc}") from exc
    return {"ok": True, "entry": _entry(target)}


def search_files(query: str, dir_rel: str = "", show_hidden: bool = False,
                 limit: int = MAX_RESULTS) -> list[dict]:
    query = query.strip()
    if not query:
        return []
    target = safe_path(dir_rel)
    if not target.is_dir():
        raise ApiError(404, "Dossier introuvable")
    needle = query.lower()
    results: list[dict] = []

    for current, dirs, files in os.walk(target, followlinks=False):
        current_path = Path(current)
        dirs[:] = sorted(
            d for d in dirs
            if d not in SKIP_DIRS and (show_hidden or not d.startswith("."))
        )
        for filename in sorted(files):
            if not show_hidden and filename.startswith("."):
                continue
            path = current_path / filename
            try:
                if path.is_symlink() and not _within(path.resolve()):
                    continue
                if path.stat().st_size > TEXT_SEARCH_LIMIT:
                    continue
                raw = path.read_bytes()
            except OSError:
                continue
            if b"\x00" in raw[:4096]:
                continue
            try:
                text = raw.decode("utf-8")
            except UnicodeDecodeError:
                continue
            for line_no, line in enumerate(text.splitlines(), 1):
                if needle in line.lower():
                    results.append({
                        "path": relpath(path),
                        "name": filename,
                        "line": line_no,
                        "text": line.strip()[:240],
                    })
                    if len(results) >= limit:
                        return results
    return results


def find_files(query: str = "", limit: int = 500) -> list[dict]:
    """Liste plate pour l'ouverture rapide (fichiers récents en premier)."""
    query = query.strip().lower()
    found: list[dict] = []
    for current, dirs, files in os.walk(PROJECTS_ROOT, followlinks=False):
        current_path = Path(current)
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS and not d.startswith(".")]
        for filename in files:
            if filename.startswith("."):
                continue
            path = current_path / filename
            rel = relpath(path)
            if query and query not in rel.lower():
                continue
            try:
                mtime = int(path.stat().st_mtime * 1000)
            except OSError:
                mtime = 0
            found.append({"path": rel, "name": filename, "mtime": mtime})
    found.sort(key=lambda item: item["mtime"], reverse=True)
    return found[:limit]


def resolve_for_run(path: str | None) -> tuple[Path | None, Path]:
    """Retourne (fichier cible, cwd) en garantissant le confinement."""
    if not path:
        return None, PROJECTS_ROOT
    target = safe_path(path)
    if not target.is_file():
        raise ApiError(404, "Fichier introuvable")
    return target, target.parent


def file_mtime(path: Path) -> int:
    try:
        return int(path.stat().st_mtime * 1000)
    except OSError:
        return 0


def now_ms() -> int:
    return int(time.time() * 1000)
