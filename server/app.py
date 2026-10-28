"""Serveur Mobile Py IDE — Starlette (sans pydantic, compatible Termux)."""

from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path

import uvicorn
from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import FileResponse, JSONResponse
from starlette.routing import Mount, Route, WebSocketRoute
from starlette.staticfiles import StaticFiles
from starlette.websockets import WebSocket, WebSocketDisconnect

from . import ai, analysis, files, packages, runner, snippets
from .config import (
    AI_KEY,
    AI_MODEL,
    AI_URL,
    APP_NAME,
    IS_ANDROID,
    PKG_BACKEND,
    HOST,
    MAX_FILE_BYTES,
    PORT,
    PROJECTS_ROOT,
    TOKEN,
    VERSION,
)

WEB_DIR = Path(__file__).resolve().parent.parent / "web"
MAX_CODE_BYTES = 2 * 1024 * 1024


# ---------- utilitaires ----------

class TokenMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # /api/health reste public : le frontend doit pouvoir savoir qu'un
        # jeton est nécessaire avant même de le demander à l'utilisateur.
        if TOKEN and request.url.path.startswith("/api") and request.url.path != "/api/health":
            supplied = request.headers.get("x-pyide-token") or request.query_params.get("token")
            if supplied != TOKEN:
                return JSONResponse({"detail": "Jeton d'accès requis"}, status_code=401)
        return await call_next(request)


async def api_error_handler(request: Request, exc: files.ApiError) -> JSONResponse:
    return JSONResponse({"detail": exc.detail}, status_code=exc.status_code)


async def body_json(request: Request) -> dict:
    try:
        data = await request.json()
    except (json.JSONDecodeError, UnicodeDecodeError):
        raise files.ApiError(400, "Corps JSON invalide")
    if not isinstance(data, dict):
        raise files.ApiError(400, "Objet JSON attendu")
    return data


def _text(data: dict, key: str, default: str = "") -> str:
    value = data.get(key, default)
    if value is None:
        return default
    if not isinstance(value, str):
        raise files.ApiError(400, f"Champ « {key} » invalide")
    return value


def _int(data: dict, key: str, default: int = 0) -> int:
    value = data.get(key, default)
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _analysis_path(value: str | None) -> str | None:
    if not value:
        return None
    return str(files.safe_path(value))


def _code(data: dict) -> str:
    code = _text(data, "code")
    if len(code.encode("utf-8")) > MAX_CODE_BYTES:
        raise files.ApiError(413, "Code trop volumineux")
    return code


# ---------- API analyse ----------

async def api_complete(request: Request):
    data = await body_json(request)
    items = analysis.complete(
        _code(data), _int(data, "line", 1), _int(data, "column", 0),
        _analysis_path(_text(data, "path") or None),
    )
    return JSONResponse({"items": items})


async def api_hover(request: Request):
    data = await body_json(request)
    markdown = analysis.hover(
        _code(data), _int(data, "line", 1), _int(data, "column", 0),
        _analysis_path(_text(data, "path") or None),
    )
    return JSONResponse({"markdown": markdown})


async def api_signature(request: Request):
    data = await body_json(request)
    result = analysis.signature(
        _code(data), _int(data, "line", 1), _int(data, "column", 0),
        _analysis_path(_text(data, "path") or None),
    )
    return JSONResponse({"signature": result})


async def api_definition(request: Request):
    data = await body_json(request)
    locations = analysis.definition(
        _code(data), _int(data, "line", 1), _int(data, "column", 0),
        _analysis_path(_text(data, "path") or None),
    )
    for location in locations:
        if not location.get("path"):
            # Définition dans le buffer courant (Jedi ne fournit pas de chemin).
            location["rel"] = None
            location["external"] = False
            continue
        try:
            path = Path(location["path"]).resolve()
            location["rel"] = files.relpath(path)
            location["absPath"] = str(path)
            location["external"] = False
        except (ValueError, OSError):
            location["rel"] = None
            location["external"] = True
            location["name"] = Path(location["path"]).name
    return JSONResponse({"locations": locations, "location": locations[0] if locations else None})


async def api_diagnose(request: Request):
    data = await body_json(request)
    markers = analysis.diagnose(
        _code(data), _analysis_path(_text(data, "path") or None)
    )
    return JSONResponse({"markers": markers})


async def api_format(request: Request):
    data = await body_json(request)
    result = analysis.format_code(_code(data))
    return JSONResponse(result)


# ---------- API fichiers ----------

async def api_tree(request: Request):
    dir_value = request.query_params.get("dir", "")
    show_hidden = request.query_params.get("hidden") in {"1", "true", "yes"}
    return JSONResponse(files.list_dir(dir_value, show_hidden=show_hidden))


async def api_read_file(request: Request):
    path = request.query_params.get("path")
    if not path:
        raise files.ApiError(400, "Chemin requis")
    return JSONResponse(files.read_file(path))


async def api_exists(request: Request):
    """Test d'existence sans provoquer de 404 dans la console du navigateur."""
    path = request.query_params.get("path")
    if not path:
        raise files.ApiError(400, "Chemin requis")
    target = files.safe_path(path)
    return JSONResponse({
        "exists": target.exists() or target.is_symlink(),
        "isDir": target.is_dir(),
    })


async def api_save_file(request: Request):
    data = await body_json(request)
    path = _text(data, "path")
    content = _text(data, "content")
    return JSONResponse(files.save_file(path, content))


async def api_mkdir(request: Request):
    data = await body_json(request)
    return JSONResponse(files.make_dir(_text(data, "path")))


async def api_rename(request: Request):
    data = await body_json(request)
    return JSONResponse(files.rename_path(
        _text(data, "path"), _text(data, "newPath")
    ))


async def api_delete(request: Request):
    data = await body_json(request)
    return JSONResponse(files.delete_path(_text(data, "path")))


async def api_upload(request: Request):
    try:
        form = await request.form()
    except Exception as exc:
        raise files.ApiError(400, f"Formulaire invalide : {exc}")
    dir_value = form.get("dir") or ""
    uploads = form.getlist("files") or form.getlist("file")
    if not uploads:
        raise files.ApiError(400, "Aucun fichier reçu")
    saved = []
    for upload in uploads:
        filename = getattr(upload, "filename", None) or "fichier"
        data = await upload.read()
        saved.append(files.upload_file(str(dir_value), filename, data))
    return JSONResponse({"ok": True, "files": saved})


async def api_download(request: Request):
    path = request.query_params.get("path")
    if not path:
        raise files.ApiError(400, "Chemin requis")
    target = files.safe_path(path)
    if not target.is_file():
        raise files.ApiError(404, "Fichier introuvable")
    return FileResponse(target, filename=target.name)


async def api_search(request: Request):
    query = request.query_params.get("q", "")
    dir_value = request.query_params.get("dir", "")
    show_hidden = request.query_params.get("hidden") in {"1", "true", "yes"}
    return JSONResponse({
        "results": files.search_files(query, dir_value, show_hidden=show_hidden)
    })


async def api_files(request: Request):
    query = request.query_params.get("q", "")
    directory = request.query_params.get("dir", "")
    return JSONResponse({"files": files.find_files(query, directory)})


async def api_places(request: Request):
    return JSONResponse({
        "places": files.places(),
        "root": str(PROJECTS_ROOT),
        "native": IS_ANDROID,
    })


async def api_add_place(request: Request):
    data = await body_json(request)
    return JSONResponse({"place": files.add_place(_text(data, "path"), _text(data, "label"))})


async def api_remove_place(request: Request):
    data = await body_json(request)
    return JSONResponse({"ok": files.remove_place(_text(data, "id"))})


async def api_import(request: Request):
    data = await body_json(request)
    return JSONResponse(files.import_path(
        _text(data, "source"), _text(data, "dir"), overwrite=bool(data.get("overwrite"))
    ))


async def api_info(request: Request):
    path = request.query_params.get("path")
    if not path:
        raise files.ApiError(400, "Chemin requis")
    return JSONResponse(files.info(path))


# ---------- API exécution ----------

async def api_run(request: Request):
    data = await body_json(request)
    code = data.get("code")
    path = data.get("path")
    if code is not None and not isinstance(code, str):
        raise files.ApiError(400, "Code invalide")
    if path is not None and not isinstance(path, str):
        raise files.ApiError(400, "Chemin invalide")
    if code is not None:
        _code(data)
    stdin = data.get("stdin")
    if stdin is not None and not isinstance(stdin, str):
        raise files.ApiError(400, "Entrée standard invalide")
    args = data.get("args") or []
    result = await runner.run_capture(
        code=code,
        path=path or None,
        stdin=stdin,
        args=args,
        timeout=data.get("timeout"),
        repl=bool(data.get("repl")),
    )
    return JSONResponse({
        "stdout": result.stdout,
        "stderr": result.stderr,
        "code": result.code,
        "duration": result.duration,
        "timedOut": result.timed_out,
        "truncated": result.truncated,
    })


async def _pump_gfx(path: Path | None, queue: asyncio.Queue,
                    wait_task: asyncio.Task) -> None:
    """Lit le fichier d'événements graphiques du programme et les relaie."""
    if path is None:
        return
    offset = 0
    while not wait_task.done():
        await asyncio.sleep(0.12)
        try:
            if not path.exists():
                continue
            with path.open("rb") as handle:
                handle.seek(offset)
                chunk = handle.read()
            end = chunk.rfind(b"\n")
            if end < 0:
                continue
            for line in chunk[: end + 1].split(b"\n"):
                line = line.strip()
                if not line:
                    continue
                try:
                    event = json.loads(line.decode("utf-8", "replace"))
                except json.JSONDecodeError:
                    continue
                if isinstance(event, dict):
                    queue.put_nowait(event)
            offset += end + 1
        except OSError:
            continue


async def ws_run(websocket: WebSocket):
    if TOKEN and websocket.query_params.get("token") != TOKEN:
        await websocket.close(code=4401)
        return
    await websocket.accept()

    queue: asyncio.Queue = asyncio.Queue()
    sender_failed = False

    async def sender():
        nonlocal sender_failed
        while True:
            message = await queue.get()
            if message is None:
                break
            try:
                await websocket.send_json(message)
            except Exception:
                sender_failed = True
                break

    sender_task = asyncio.create_task(sender())
    session: runner.RunSession | None = None
    recv_task: asyncio.Task | None = None
    gfx_task: asyncio.Task | None = None

    try:
        try:
            start = await asyncio.wait_for(websocket.receive_json(), timeout=30)
        except (asyncio.TimeoutError, WebSocketDisconnect, json.JSONDecodeError):
            return
        if not isinstance(start, dict) or start.get("type") != "start":
            queue.put_nowait({"type": "error", "message": "Message « start » attendu"})
            return

        code = start.get("code")
        path = start.get("path")
        if code is not None and not isinstance(code, str):
            raise files.ApiError(400, "Code invalide")
        if path is not None and not isinstance(path, str):
            raise files.ApiError(400, "Chemin invalide")
        if code is not None and len(code.encode("utf-8")) > MAX_CODE_BYTES:
            raise files.ApiError(413, "Code trop volumineux")

        spec = runner.build_spec(
            code=code,
            path=path or None,
            args=start.get("args") or [],
            timeout=start.get("timeout"),
            repl=bool(start.get("repl")),
        )
        session = runner.RunSession(spec)

        async def on_output(stream: str, text: str) -> None:
            queue.put_nowait({"type": stream, "data": text})

        await session.start(on_output)
        queue.put_nowait({"type": "started", "pid": session.proc.pid if session.proc else None,
                          "cwd": str(spec.cwd), "repl": bool(start.get("repl"))})

        wait_task = asyncio.create_task(session.wait())
        gfx_task = asyncio.create_task(_pump_gfx(spec.gfx_file, queue, wait_task))
        recv_task = asyncio.create_task(websocket.receive_json())

        while not wait_task.done():
            done, _ = await asyncio.wait(
                {wait_task, recv_task}, return_when=asyncio.FIRST_COMPLETED
            )
            if recv_task in done:
                try:
                    message = recv_task.result()
                except (WebSocketDisconnect, json.JSONDecodeError, RuntimeError):
                    await session.stop()
                    break
                if not isinstance(message, dict):
                    message = {}
                kind = message.get("type")
                if kind == "stdin":
                    data = message.get("data")
                    if isinstance(data, str):
                        await session.send_stdin(data)
                elif kind == "close_stdin":
                    await session.close_stdin()
                elif kind == "gfx_input":
                    payload = message.get("event")
                    if isinstance(payload, dict) and spec.gfx_in is not None:
                        try:
                            with spec.gfx_in.open("a", encoding="utf-8") as handle:
                                handle.write(json.dumps(payload) + "\n")
                        except OSError:
                            pass
                elif kind == "stop":
                    queue.put_nowait({"type": "stopping"})
                    await session.stop()
                recv_task = asyncio.create_task(websocket.receive_json())
            if sender_failed:
                await session.stop()
                break

        result = await wait_task
        if gfx_task:
            gfx_task.cancel()
        queue.put_nowait({
            "type": "exit",
            "code": result.code,
            "duration": result.duration,
            "timedOut": result.timed_out,
            "truncated": result.truncated,
        })
    except files.ApiError as exc:
        queue.put_nowait({"type": "error", "message": exc.detail})
    except WebSocketDisconnect:
        if session:
            await session.stop()
    except Exception as exc:
        queue.put_nowait({"type": "error", "message": f"Erreur serveur : {exc}"})
    finally:
        if recv_task:
            recv_task.cancel()
        if gfx_task:
            gfx_task.cancel()
        if session:
            await session.stop()
        queue.put_nowait(None)
        try:
            await asyncio.wait_for(sender_task, timeout=2)
        except asyncio.TimeoutError:
            sender_task.cancel()
        try:
            await websocket.close()
        except Exception:
            pass


# ---------- API paquets / snippets / IA ----------

async def api_packages(request: Request):
    return JSONResponse(await packages.list_packages())


async def api_install_package(request: Request):
    data = await body_json(request)
    result = await packages.install_package(
        _text(data, "name"), upgrade=bool(data.get("upgrade"))
    )
    return JSONResponse(result)


async def api_uninstall_package(request: Request):
    data = await body_json(request)
    return JSONResponse(await packages.uninstall_package(_text(data, "name")))


async def api_package_catalog(request: Request):
    return JSONResponse({
        "catalog": packages.catalog(),
        "backend": PKG_BACKEND,
        "graphics": packages.GRAPHICS_PACKAGES,
    })


async def api_package_search(request: Request):
    query = request.query_params.get("q", "")
    try:
        results = await packages.search(query)
    except files.ApiError as exc:
        raise files.ApiError(exc.status_code, exc.detail)
    return JSONResponse({"results": results, "query": query})


async def api_package_info(request: Request):
    name = request.query_params.get("name", "")
    if not name:
        raise files.ApiError(400, "Nom requis")
    return JSONResponse(await packages.metadata(name))


async def api_snippets(request: Request):
    return JSONResponse({"snippets": snippets.list_snippets()})


async def api_ai_status(request: Request):
    return JSONResponse(ai.status())


async def api_ai_ask(request: Request):
    data = await body_json(request)
    result = await ai.ask(
        mode=_text(data, "mode", "explain"),
        code=_text(data, "code"),
        question=_text(data, "question"),
        path=_text(data, "path") or None,
        selection=_text(data, "selection"),
    )
    return JSONResponse(result)


# ---------- santé / frontend ----------

async def api_health(request: Request):
    return JSONResponse({
        "ok": True,
        "app": APP_NAME,
        "version": VERSION,
        "python": sys.version.split()[0],
        "root": str(PROJECTS_ROOT),
        "authRequired": bool(TOKEN),
        "native": IS_ANDROID,
        "pkgBackend": PKG_BACKEND,
        "places": files.places(),
        "features": {
            "websocket": True,
            "format": True,
            "packages": True,
            "graphics": True,
            "ai": bool(AI_URL or AI_MODEL),
        },
    })


async def index(request: Request):
    response = FileResponse(WEB_DIR / "index.html")
    response.headers["Cache-Control"] = "no-cache"
    return response


async def favicon(request: Request):
    return FileResponse(WEB_DIR / "favicon.svg")


app = Starlette(
    routes=[
        Route("/", index),
        Route("/favicon.svg", favicon),
        Route("/api/health", api_health),
        Route("/api/complete", api_complete, methods=["POST"]),
        Route("/api/hover", api_hover, methods=["POST"]),
        Route("/api/signature", api_signature, methods=["POST"]),
        Route("/api/definition", api_definition, methods=["POST"]),
        Route("/api/diagnose", api_diagnose, methods=["POST"]),
        Route("/api/format", api_format, methods=["POST"]),
        Route("/api/tree", api_tree),
        Route("/api/file", api_read_file, methods=["GET"]),
        Route("/api/file", api_save_file, methods=["POST"]),
        Route("/api/exists", api_exists),
        Route("/api/mkdir", api_mkdir, methods=["POST"]),
        Route("/api/rename", api_rename, methods=["POST"]),
        Route("/api/delete", api_delete, methods=["POST"]),
        Route("/api/upload", api_upload, methods=["POST"]),
        Route("/api/download", api_download),
        Route("/api/search", api_search),
        Route("/api/files", api_files),
        Route("/api/places", api_places),
        Route("/api/info", api_info),
        Route("/api/places/add", api_add_place, methods=["POST"]),
        Route("/api/places/remove", api_remove_place, methods=["POST"]),
        Route("/api/import", api_import, methods=["POST"]),
        Route("/api/run", api_run, methods=["POST"]),
        WebSocketRoute("/ws/run", ws_run),
        Route("/api/packages", api_packages),
        Route("/api/packages/install", api_install_package, methods=["POST"]),
        Route("/api/packages/uninstall", api_uninstall_package, methods=["POST"]),
        Route("/api/packages/catalog", api_package_catalog),
        Route("/api/packages/search", api_package_search),
        Route("/api/packages/info", api_package_info),
        Route("/api/snippets", api_snippets),
        Route("/api/ai/status", api_ai_status),
        Route("/api/ai", api_ai_ask, methods=["POST"]),
        Mount("/static", app=StaticFiles(directory=WEB_DIR), name="static"),
        # Sert aussi index.html et les ressources relatives (style.css, app.js…)
        Mount("/", app=StaticFiles(directory=WEB_DIR, html=True), name="web"),
    ],
    middleware=[Middleware(TokenMiddleware)],
    exception_handlers={files.ApiError: api_error_handler},
    max_body_size=max(MAX_FILE_BYTES * 2, 32 * 1024 * 1024),
)


def main() -> None:
    print(f"{APP_NAME} {VERSION} → http://127.0.0.1:{PORT}")
    print(f"Dossier projets : {PROJECTS_ROOT}")
    print(f"Python : {sys.version.split()[0]} — IA : {'configurée' if (AI_URL or AI_MODEL) else 'optionnelle'}")
    if HOST not in {"127.0.0.1", "localhost", "::1"} and not TOKEN:
        print("⚠️  Serveur exposé sur le réseau SANS jeton (PYIDE_TOKEN).")
        print("   Toute personne du Wi-Fi peut exécuter du code sur ce téléphone.")
    uvicorn.run(
        app, host=HOST, port=PORT, log_level="warning",
        ws_ping_interval=20, ws_ping_timeout=20,
    )


if __name__ == "__main__":
    main()
