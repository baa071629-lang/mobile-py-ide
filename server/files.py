"""Opérations fichiers sécurisées, confinées aux racines autorisées.

Trois familles d'emplacements (« places ») sont accessibles :

* le dossier des projets (``PYIDE_PROJECTS``, toujours accessible) ;
* le dossier personnel de l'utilisateur ;
* le stockage partagé du téléphone (``/sdcard``, ``/storage/emulated/0``…)
  et tous les dossiers ajoutés via ``PYIDE_ROOTS``.

Les chemins manipulés par l'API sont **absolus** ; les chemins relatifs sont
résolus dans le dossier des projets (compatibilité ascendante).
"""

from __future__ import annotations

import os
import shutil
import time
import uuid
from pathlib import Path

from .config import (
    MAX_FILE_BYTES,
    MAX_RESULTS,
    MAX_UPLOAD_BYTES,
    PLACES,
    PROJECTS_ROOT,
    ROOTS,
)

SKIP_DIRS = {
    ".git", ".hg", ".svn", ".venv", "venv", "env", "__pycache__",
    "node_modules", ".mypy_cache", ".pytest_cache", ".ruff_cache",
    ".idea", ".vscode", ".pyide-trash",
}
TEXT_SEARCH_LIMIT = 1 * 1024 * 1024
IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".svg", ".ico"}


_PLACES: list[dict] = [dict(place) for place in PLACES]
_ROOTS: list[Path] = [Path(place["path"]) for place in PLACES]


class ApiError(Exception):
    def __init__(self, status_code: int, detail: str):
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


# ---------- racines autorisées ----------

def places() -> list[dict]:
    """Liste des emplacements proposés dans le sélecteur de dossiers."""
    result = []
    for place in _PLACES:
        path = Path(place["path"])
        writable = True
        try:
            writable = os.access(path, os.W_OK)
        except OSError:
            writable = False
        entry = dict(place)
        entry["writable"] = writable
        entry["isProjects"] = path == PROJECTS_ROOT
        result.append(entry)
    return result


def add_place(value: str, label: str = "") -> dict:
    """Ajoute un dossier accessible (persisté jusqu'au redémarrage du serveur)."""
    raw = (value or "").strip()
    if not raw:
        raise ApiError(400, "Chemin requis")
    candidate = Path(raw).expanduser()
    try:
        resolved = candidate.resolve()
    except OSError as exc:
        raise ApiError(400, f"Chemin invalide : {exc}") from exc
    if not resolved.is_dir():
        raise ApiError(404, "Dossier introuvable")
    for place in _PLACES:
        if Path(place["path"]) == resolved:
            return place
    place = {
        "id": f"place{len(_PLACES)}",
        "label": (label or resolved.name or str(resolved))[:60],
        "path": str(resolved),
        "kind": "extra",
    }
    _PLACES.append(place)
    _ROOTS.append(resolved)
    return place


def remove_place(place_id: str) -> bool:
    for index, place in enumerate(_PLACES):
        if place["id"] != place_id:
            continue
        if place["kind"] in {"projects", "home", "shared"}:
            raise ApiError(400, "Cet emplacement ne peut pas être retiré")
        _PLACES.pop(index)
        path = Path(place["path"])
        if path in _ROOTS:
            _ROOTS.remove(path)
        return True
    return False


def place_for(path: Path) -> dict | None:
    for place in _PLACES:
        root = Path(place["path"])
        if path == root or root in path.parents:
            return place
    return None


def _allowed(path: Path) -> bool:
    for root in _ROOTS:
        if path == root or root in path.parents:
            return True
    return False


def _within(path: Path) -> bool:  # compatibilité avec l'ancien nom
    return _allowed(path)


def safe_path(value: str | None) -> Path:
    """Résout un chemin sans jamais sortir des emplacements autorisés."""
    value = (value or "").strip()
    if "\x00" in value:
        raise ApiError(400, "Chemin invalide")
    raw = Path(value).expanduser() if value else PROJECTS_ROOT
    if not raw.is_absolute():
        raw = PROJECTS_ROOT / raw
    try:
        resolved = raw.resolve()
    except (OSError, RuntimeError):
        raise ApiError(400, "Chemin invalide")
    if not _allowed(resolved):
        raise ApiError(403, "Dossier non autorisé")
    return resolved


def relpath(path: Path) -> str:
    """Chemin relatif à son emplacement (affichage), sinon chemin absolu."""
    for place in _PLACES:
        root = Path(place["path"])
        if path == root:
            return ""
        if root in path.parents:
            return path.relative_to(root).as_posix()
    return path.as_posix()


def abspath(value: str | None) -> str:
    return str(safe_path(value))


def _validate_name(name: str) -> str:
    name = name.strip()
    if not name or name in {".", ".."} or "/" in name or "\\" in name or "\x00" in name:
        raise ApiError(400, "Nom de fichier invalide")
    return name


def _is_temp(path: Path) -> bool:
    return path.name.startswith(".pyide-")


def _kind(path: Path) -> str:
    if path.is_dir():
        return "dir"
    suffix = path.suffix.lower()
    if suffix == ".py":
        return "python"
    if suffix in IMAGE_SUFFIXES:
        return "image"
    return "file"


def _entry(path: Path) -> dict:
    try:
        stat = path.stat()
    except OSError:
        stat = None
    place = place_for(path)
    return {
        "name": path.name,
        "isDir": path.is_dir(),
        "path": str(path),
        "rel": relpath(path),
        "place": place["id"] if place else None,
        "size": stat.st_size if stat and path.is_file() else 0,
        "mtime": int(stat.st_mtime * 1000) if stat else 0,
        "kind": _kind(path),
    }


def info(value: str | None) -> dict:
    path = safe_path(value)
    if not (path.exists() or path.is_symlink()):
        raise ApiError(404, "Chemin introuvable")
    return _entry(path)


def list_dir(dir_rel: str = "", show_hidden: bool = False) -> dict:
    target = safe_path(dir_rel)
    if not target.is_dir():
        raise ApiError(404, "Dossier introuvable")

    entries: list[dict] = []
    try:
        children = list(target.iterdir())
    except OSError as exc:
        raise ApiError(403, f"Dossier illisible : {exc}") from exc

    for entry in children:
        if not show_hidden and entry.name.startswith("."):
            continue
        if _is_temp(entry):
            continue
        try:
            if entry.is_symlink() and not _allowed(entry.resolve()):
                continue
        except OSError:
            continue
        entries.append(_entry(entry))
    entries.sort(key=lambda e: (not e["isDir"], e["name"].lower()))

    place = place_for(target)
    parent = None
    if place:
        root = Path(place["path"])
        parent = None if target == root else str(target.parent)
    elif target.parent != target:
        parent = str(target.parent)
    return {
        "root": str(PROJECTS_ROOT),
        "place": place["id"] if place else None,
        "dir": str(target),
        "parent": parent,
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
        "path": str(target),
        "rel": relpath(target),
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
    if target.is_dir():
        raise ApiError(400, "Le chemin désigne un dossier")
    _atomic_write(target, content)
    stat = target.stat()
    return {
        "ok": True, "path": str(target), "rel": relpath(target),
        "size": stat.st_size, "mtime": int(stat.st_mtime * 1000),
    }


def make_dir(path: str) -> dict:
    target = safe_path(path)
    place = place_for(target)
    if place and Path(place["path"]) == target:
        raise ApiError(400, "Dossier déjà existant")
    if target.exists():
        raise ApiError(409, "Ce chemin existe déjà")
    try:
        target.mkdir(parents=True)
    except OSError as exc:
        raise ApiError(500, f"Création impossible : {exc}") from exc
    return {"ok": True, "path": str(target), "rel": relpath(target)}


def rename_path(path: str, new_path: str) -> dict:
    source = safe_path(path)
    place = place_for(source)
    if place and Path(place["path"]) == source:
        raise ApiError(400, "Impossible de renommer la racine")
    if not source.exists():
        raise ApiError(404, "Chemin introuvable")
    destination = safe_path(new_path)
    _validate_name(destination.name)
    if destination == source:
        return {"ok": True, "path": str(source), "rel": relpath(source)}
    if destination.exists():
        raise ApiError(409, "La destination existe déjà")
    try:
        destination.parent.mkdir(parents=True, exist_ok=True)
        source.rename(destination)
    except OSError as exc:
        raise ApiError(500, f"Renommage impossible : {exc}") from exc
    return {"ok": True, "path": str(destination), "rel": relpath(destination)}


def delete_path(path: str) -> dict:
    target = safe_path(path)
    place = place_for(target)
    if place and Path(place["path"]) == target:
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


def import_path(source: str, dest_dir: str, *, overwrite: bool = False) -> dict:
    """Copie un fichier/dossier externe (ex. choisi via le sélecteur Android)."""
    src = Path(source).expanduser()
    if not src.exists():
        raise ApiError(404, "Source introuvable")
    dest = safe_path(dest_dir)
    if not dest.is_dir():
        raise ApiError(404, "Dossier de destination introuvable")
    name = unique_name(dest, src.name) if not overwrite else _validate_name(src.name)
    target = dest / name
    try:
        if src.is_dir():
            shutil.copytree(src, target, dirs_exist_ok=overwrite, symlinks=False)
        else:
            shutil.copy2(src, target)
    except (OSError, shutil.Error) as exc:
        raise ApiError(500, f"Import impossible : {exc}") from exc
    return {"ok": True, "entry": _entry(target)}


def search_files(query: str, dir_rel: str = "", show_hidden: bool = False,
                 limit: int = MAX_RESULTS) -> list[dict]:
    needle = (query or "").strip().lower()
    if not needle:
        return []
    target = safe_path(dir_rel)
    if not target.is_dir():
        raise ApiError(404, "Dossier introuvable")
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
                if path.is_symlink() and not _allowed(path.resolve()):
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
                        "path": str(path),
                        "rel": relpath(path),
                        "name": filename,
                        "line": line_no,
                        "text": line.strip()[:240],
                    })
                    if len(results) >= limit:
                        return results
    return results


def find_files(query: str = "", dir_rel: str = "", limit: int = 500) -> list[dict]:
    """Liste plate pour l'ouverture rapide (fichiers récents en premier)."""
    needle = (query or "").strip().lower()
    base = safe_path(dir_rel)
    found: list[dict] = []
    for current, dirs, files in os.walk(base, followlinks=False):
        current_path = Path(current)
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS and not d.startswith(".")]
        for filename in files:
            if filename.startswith("."):
                continue
            path = current_path / filename
            rel = relpath(path)
            if needle and needle not in rel.lower():
                continue
            try:
                mtime = int(path.stat().st_mtime * 1000)
            except OSError:
                mtime = 0
            found.append({
                "path": str(path), "rel": rel, "name": filename, "mtime": mtime,
            })
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
