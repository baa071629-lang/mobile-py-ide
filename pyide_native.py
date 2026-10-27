"""Pont Python ↔ application Android (Chaquopy).

Kotlin appelle ``init`` au démarrage, puis :

* ``request``  : opération synchrone (fichiers, analyse, paquets…) ;
* ``start_run``: lance un programme dans un fil dédié et renvoie son identifiant ;
* ``run_input`` / ``run_close_stdin`` / ``stop_run`` : pilotent l'entrée du programme.

Aucune socket n'est nécessaire : tout passe par l'interface JavaScript
``window.PyAndroid``. Le code partagé (``server/*``) reste identique au mode
Termux.
"""

from __future__ import annotations

import json
import os
import sys
import threading
import traceback

_state = {
    "ready": False,
    "runs": {},
    "seq": 0,
    "root": "",
    "files_dir": "",
    "cache_dir": "",
    "storage": "",
    "version": "3.0.0",
}
_lock = threading.Lock()


class BridgeError(Exception):
    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status
        self.message = message


def _invoke(callback, method: str, *args):
    """Appelle une méthode d'un objet Kotlin (Chaquopy) ou Python (tests)."""
    call_attr = getattr(callback, "callAttr", None)
    if callable(call_attr):
        return call_attr(method, *args)
    return getattr(callback, method)(*args)


def _reload_server() -> None:
    for name in [m for m in list(sys.modules) if m == "server" or m.startswith("server.")]:
        del sys.modules[name]


def init(payload_json: str) -> str:
    """Configure l'environnement Python à partir des chemins Android."""
    info = json.loads(payload_json or "{}")
    files_dir = info.get("filesDir") or os.path.expanduser("~")
    cache_dir = info.get("cacheDir") or files_dir
    storage = info.get("storage") or ""

    projects = os.path.join(files_dir, "projects")
    site = os.path.join(files_dir, "packages")
    for path in (projects, site, cache_dir):
        try:
            os.makedirs(path, exist_ok=True)
        except OSError:
            pass

    os.environ["PYIDE_NATIVE"] = "1"
    os.environ["PYIDE_PROJECTS"] = projects
    os.environ["PYIDE_PKG_BACKEND"] = "wheels"
    os.environ["PYIDE_USER_SITE"] = site
    os.environ["PYIDE_APP_CACHE"] = cache_dir
    if storage and os.path.isdir(storage):
        os.environ["PYIDE_ROOTS"] = storage
    os.environ.setdefault("MPLBACKEND", "Agg")
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")
    if site not in sys.path:
        sys.path.insert(0, site)

    _state.update({
        "files_dir": files_dir, "cache_dir": cache_dir, "storage": storage,
        "root": projects, "version": info.get("version") or "3.0.0",
    })
    _reload_server()
    from server import config, files

    _state["ready"] = True
    _seed_project(projects)
    return json.dumps({
        "root": str(config.PROJECTS_ROOT),
        "places": files.places(),
        "python": sys.version.split()[0],
        "userSite": str(config.USER_SITE),
        "version": _state["version"],
    }, ensure_ascii=False)


def _seed_project(projects: str) -> None:
    welcome = os.path.join(projects, "bienvenue.py")
    if os.path.exists(welcome):
        return
    try:
        with open(welcome, "w", encoding="utf-8") as handle:
            handle.write(
                "# Bienvenue dans Mobile Py IDE !\n"
                "# ▶ pour exécuter, ☰ pour les fichiers, ⫿ pour la sortie.\n\n"
                "nom = input(\"Ton nom ? \")\n"
                "print(\"Salut\", nom)\n\n"
                "from pyide_gui import screen\n"
                "s = screen(320, 200, \"#101018\")\n"
                "s.circle(160, 100, 55, \"#89b4fa\")\n"
                "s.text(20, 20, \"Écran graphique\", \"#cdd6f4\")\n"
                "s.present()\n"
            )
    except OSError:
        pass


def _require_ready() -> None:
    if not _state["ready"]:
        raise BridgeError("Python n'est pas encore initialisé", 503)


# ---------- opérations synchrones ----------

def request(payload_json: str) -> str:
    """Exécute une opération et renvoie du JSON (jamais d'exception vers Kotlin)."""
    try:
        payload = json.loads(payload_json or "{}")
    except json.JSONDecodeError:
        return json.dumps({"error": "Requête illisible", "status": 400})
    op = payload.get("op") or ""
    try:
        _require_ready()
        data = _dispatch(op, payload)
        return json.dumps(data if data is not None else {"ok": True}, ensure_ascii=False)
    except BridgeError as exc:
        return json.dumps({"error": exc.message, "status": exc.status}, ensure_ascii=False)
    except Exception as exc:  # noqa: BLE001 - on renvoie l'erreur à l'interface
        status = getattr(exc, "status_code", 500)
        detail = _friendly_error(exc)
        return json.dumps({"error": detail, "status": status}, ensure_ascii=False)


def _friendly_error(exc: Exception) -> str:
    try:
        from server.files import ApiError
        if isinstance(exc, ApiError):
            return exc.detail
    except Exception:
        pass
    return f"{exc.__class__.__name__} : {exc}"


def _dispatch(op: str, payload: dict):
    import asyncio

    from server import ai, analysis, files, packages, snippets

    if op == "health":
        return {
            "ok": True, "app": "Mobile Py IDE", "version": _state["version"],
            "python": sys.version.split()[0], "root": _state["root"],
            "authRequired": False, "native": True, "pkgBackend": "wheels",
            "places": files.places(),
            "features": {"websocket": False, "format": True, "packages": True,
                         "graphics": True, "ai": bool(ai.status().get("available"))},
        }
    if op == "places":
        return {"places": files.places(), "root": _state["root"], "native": True}
    if op in {"places.add", "add_place"}:
        return {"place": files.add_place(payload.get("path", ""), payload.get("label", ""))}
    if op in {"places.remove", "remove_place"}:
        return {"ok": files.remove_place(payload.get("id", ""))}

    if op == "tree":
        return files.list_dir(payload.get("dir", ""), show_hidden=bool(payload.get("hidden")))
    if op == "file.read":
        return files.read_file(payload.get("path", ""))
    if op == "file.save":
        return files.save_file(payload.get("path", ""), payload.get("content", ""))
    if op == "exists":
        path = files.safe_path(payload.get("path"))
        return {"exists": path.exists() or path.is_symlink(), "isDir": path.is_dir()}
    if op == "info":
        return files.info(payload.get("path"))
    if op == "mkdir":
        return files.make_dir(payload.get("path", ""))
    if op == "rename":
        return files.rename_path(payload.get("path", ""), payload.get("newPath", ""))
    if op == "delete":
        return files.delete_path(payload.get("path", ""))
    if op == "import":
        return files.import_path(payload.get("source", ""), payload.get("dir", ""),
                                 overwrite=bool(payload.get("overwrite")))
    if op == "search":
        return {"results": files.search_files(
            payload.get("q", ""), payload.get("dir", ""), show_hidden=bool(payload.get("hidden"))
        )}
    if op == "files":
        return {"files": files.find_files(payload.get("q", ""), payload.get("dir", ""))}

    if op == "format":
        return analysis.format_code(payload.get("code", ""))
    if op == "complete":
        return {"items": analysis.complete(
            payload.get("code", ""), int(payload.get("line") or 1),
            int(payload.get("column") or 0), _analysis_path(payload.get("path")))}
    if op == "hover":
        return {"markdown": analysis.hover(
            payload.get("code", ""), int(payload.get("line") or 1),
            int(payload.get("column") or 0), _analysis_path(payload.get("path")))}
    if op == "signature":
        return {"signature": analysis.signature(
            payload.get("code", ""), int(payload.get("line") or 1),
            int(payload.get("column") or 0), _analysis_path(payload.get("path")))}
    if op == "diagnose":
        return {"markers": analysis.diagnose(
            payload.get("code", ""), _analysis_path(payload.get("path")))}
    if op == "definition":
        return _definition(payload)

    if op == "packages.list":
        return asyncio.run(packages.list_packages())
    if op == "packages.install":
        return asyncio.run(packages.install_package(
            payload.get("name", ""), upgrade=bool(payload.get("upgrade"))))
    if op == "packages.uninstall":
        return asyncio.run(packages.uninstall_package(payload.get("name", "")))
    if op == "packages.catalog":
        return {"catalog": packages.catalog(), "backend": "wheels",
                "graphics": packages.GRAPHICS_PACKAGES}
    if op == "packages.search":
        return {"results": asyncio.run(packages.search(payload.get("q", ""))),
                "query": payload.get("q", "")}
    if op == "packages.info":
        return asyncio.run(packages.metadata(payload.get("name", "")))

    if op == "snippets":
        return {"snippets": snippets.list_snippets()}
    if op == "ai.status":
        return ai.status()
    if op == "ai.ask":
        return asyncio.run(ai.ask(
            mode=payload.get("mode", "explain"), code=payload.get("code", ""),
            question=payload.get("question", ""), path=payload.get("path"),
            selection=payload.get("selection", ""),
        ))
    raise BridgeError(f"Opération inconnue : {op}", 404)


def _analysis_path(value):
    if not value:
        return None
    from server import files
    return str(files.safe_path(value))


def _definition(payload: dict):
    from server import analysis, files
    locations = analysis.definition(
        payload.get("code", ""), int(payload.get("line") or 1),
        int(payload.get("column") or 0), _analysis_path(payload.get("path")),
    )
    for location in locations:
        if not location.get("path"):
            location["rel"] = None
            location["external"] = False
            continue
        try:
            resolved = files.safe_path(location["path"])
            location["rel"] = files.relpath(resolved)
            location["absPath"] = str(resolved)
            location["external"] = False
        except Exception:
            location["external"] = True
    return {"locations": locations, "location": locations[0] if locations else None}


# ---------- exécution ----------

def start_run(payload_json: str, run_id: str, callback) -> str:
    """Lance un programme dans un fil dédié ; les événements passent par callback."""
    _require_ready()
    from server import native

    payload = json.loads(payload_json or "{}")

    def emit(event: dict) -> None:
        message = dict(event)
        message["runId"] = run_id
        try:
            _invoke(callback, "onEvent", run_id, json.dumps(message, ensure_ascii=False))
        except Exception:
            pass

    session = native.NativeSession(
        emit,
        code=payload.get("code"),
        path=payload.get("path"),
        args=payload.get("args") or [],
        timeout=payload.get("timeout") or 30,
        repl=bool(payload.get("repl")),
    )
    with _lock:
        _state["seq"] += 1
        _state["runs"][run_id] = session
    session.start()
    return run_id


def run_input(run_id: str, text: str) -> bool:
    session = _state["runs"].get(run_id)
    if not session:
        return False
    return session.send_stdin(text)


def run_close_stdin(run_id: str) -> bool:
    session = _state["runs"].get(run_id)
    if not session:
        return False
    session.close_stdin()
    return True


def stop_run(run_id: str) -> bool:
    session = _state["runs"].get(run_id)
    if not session:
        return False
    session.stop()
    return True


def cleanup_run(run_id: str) -> bool:
    with _lock:
        return bool(_state["runs"].pop(run_id, None))


def python_info() -> str:
    return json.dumps({
        "python": sys.version,
        "executable": sys.executable,
        "path": sys.path[:8],
        "ready": _state["ready"],
    }, ensure_ascii=False)
