"""Serveur graphique interne : flux d'opérations + file d'événements d'entrée.

Le programme dessine (pygame, tkinter, canevas `pyide_gui`) et ses opérations
sont envoyées à l'interface, qui les rend sur un canevas plein écran. Les
touchers et le clavier remontent dans la file d'événements lue par le module
`pygame`.

Deux transports pour l'entrée :

* **application Android** : appel direct `gfx_event()` depuis le pont Kotlin ;
* **serveur Termux/PC** : fichier `PYIDE_GFX_IN` alimenté par la WebSocket.
"""

from __future__ import annotations

import json
import os
import threading
import time
from collections import deque
from pathlib import Path

MAX_PENDING_EVENTS = 512


class GraphicsServer:
    def __init__(self) -> None:
        self._emit = None
        self._lock = threading.RLock()
        self._cv = threading.Condition(self._lock)
        self._events: deque[dict] = deque(maxlen=MAX_PENDING_EVENTS)
        self._batch: list[dict] = []
        self._open = False
        self._closed = False
        self._out_path = Path(os.environ["PYIDE_GFX_FILE"]) if os.environ.get("PYIDE_GFX_FILE") else None
        self._in_path = Path(os.environ["PYIDE_GFX_IN"]) if os.environ.get("PYIDE_GFX_IN") else None
        self._in_offset = 0
        self.width = 640
        self.height = 480
        self.fullscreen = False
        self.title = ""
        self._keys: dict[str, bool] = {}
        self._mouse = (0, 0)
        self._buttons = (False, False, False)

    # ---------- sortie (Python → interface) ----------
    def bind(self, emit) -> None:
        self._emit = emit

    def _send(self, event: dict) -> None:
        emit = self._emit
        if emit is None:
            # Mode sous-processus : on écrit le flux dans le fichier lu par le serveur.
            if self._out_path is not None:
                try:
                    with self._out_path.open("a", encoding="utf-8") as handle:
                        handle.write(json.dumps(event, ensure_ascii=False) + "\n")
                except OSError:
                    pass
            return
        try:
            emit(event)
        except Exception:
            pass

    def open(self, width: int = 640, height: int = 480, background: str = "#000000",
             fullscreen: bool = False, title: str = "", mode: str = "") -> None:
        self.width = max(int(width), 1)
        self.height = max(int(height), 1)
        self.fullscreen = bool(fullscreen)
        self.title = title or ""
        self._open = True
        self._closed = False
        self._send({
            "type": "gfx", "op": "open", "width": self.width, "height": self.height,
            "background": background, "fullscreen": self.fullscreen,
            "title": self.title, "mode": mode,
        })

    @property
    def is_open(self) -> bool:
        return self._open and not self._closed

    def op(self, name: str, **payload) -> None:
        """Ajoute une primitive ; envoyée au prochain `present()`."""
        if self._closed:
            return
        event = {"op": name}
        event.update(payload)
        with self._lock:
            if self._open:
                self._batch.append(event)
            else:
                self._send({"type": "gfx", **event})

    def emit_now(self, event: dict) -> None:
        payload = {"type": "gfx"}
        payload.update(event)
        self._send(payload)

    def present(self) -> None:
        with self._lock:
            if self._closed:
                return
            if not self._batch:
                self._send({"type": "gfx", "op": "present"})
                return
            batch, self._batch = self._batch, []
        self._send({"type": "gfx", "op": "frame", "ops": batch})

    def set_title(self, title: str) -> None:
        self.title = str(title or "")
        self._send({"type": "gfx", "op": "title", "title": self.title})

    def set_fullscreen(self, value: bool) -> None:
        self.fullscreen = bool(value)
        self._send({"type": "gfx", "op": "fullscreen", "value": self.fullscreen})

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        self._open = False
        self._send({"type": "gfx", "op": "close"})

    # ---------- entrée (interface → Python) ----------
    def push_event(self, event: dict) -> None:
        if not isinstance(event, dict):
            return
        kind = event.get("type")
        with self._cv:
            if kind == "key":
                name = str(event.get("name", "")).upper()
                self._keys[name] = bool(event.get("down"))
            elif kind == "mouse":
                self._mouse = (int(event.get("x", 0)), int(event.get("y", 0)))
                buttons = event.get("buttons")
                if isinstance(buttons, list) and len(buttons) >= 3:
                    self._buttons = tuple(bool(b) for b in buttons[:3])  # type: ignore[assignment]
            self._events.append(event)
            self._cv.notify_all()

    def _drain_input_file(self) -> None:
        path = self._in_path
        if path is None:
            return
        try:
            if not path.exists():
                return
            with path.open("rb") as handle:
                handle.seek(self._in_offset)
                chunk = handle.read()
            # On ne consomme que les lignes terminées : une écriture en cours
            # reste dans le fichier pour la lecture suivante.
            end = chunk.rfind(b"\n")
            if end < 0:
                return
            for line in chunk[: end + 1].split(b"\n"):
                line = line.strip()
                if not line:
                    continue
                try:
                    self.push_event(json.loads(line.decode("utf-8", "replace")))
                except json.JSONDecodeError:
                    continue
            self._in_offset += end + 1
        except OSError:
            return

    def poll(self) -> list[dict]:
        self._drain_input_file()
        with self._cv:
            events = list(self._events)
            self._events.clear()
        return events

    def wait(self, timeout: float = 0.0) -> list[dict]:
        deadline = time.monotonic() + max(timeout, 0.0)
        while True:
            events = self.poll()
            if events:
                return events
            if timeout and time.monotonic() >= deadline:
                return []
            with self._cv:
                self._cv.wait(0.02)

    def peek_quit(self) -> bool:
        self._drain_input_file()
        with self._cv:
            for event in self._events:
                if event.get("type") == "quit":
                    return True
        return False

    @property
    def keys(self) -> dict[str, bool]:
        with self._cv:
            return dict(self._keys)

    @property
    def mouse(self) -> tuple[int, int]:
        with self._cv:
            return self._mouse

    @property
    def buttons(self) -> tuple[bool, bool, bool]:
        with self._cv:
            return self._buttons


SERVER = GraphicsServer()


def server() -> GraphicsServer:
    return SERVER


def reset() -> None:
    """Prépare le serveur pour une nouvelle exécution."""
    global SERVER
    SERVER = GraphicsServer()
