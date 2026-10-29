"""Canevas graphique utilisable depuis les programmes exécutés dans l'IDE.

    from pyide_gui import screen
    s = screen()
    s.clear("#101020")
    s.circle(200, 120, 60, "#89b4fa")
    s.text(10, 20, "Bonjour", "#ffffff")
    s.present()

Sur Android, les opérations sont envoyées à l'écran graphique de l'IDE.
Dans le navigateur (serveur Termux), elles passent par un fichier d'événements
lu en temps réel par le serveur.
"""

from __future__ import annotations

import json
import os

_EVENTS_FILE = os.environ.get("PYIDE_GFX_FILE", "").strip()


def _file_emitter(event: dict) -> None:
    try:
        with open(_EVENTS_FILE, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(event, ensure_ascii=False) + "\n")
    except OSError:
        pass


def _install_emitter() -> None:
    try:
        from server import gui
    except Exception:  # pragma: no cover - mode autonome
        return
    if _EVENTS_FILE:
        gui.set_emitter(_file_emitter)
    try:
        gui.install_hooks()
    except Exception:
        pass


_install_emitter()

try:
    from server.gui import Canvas, screen, show_image, show_file, emit  # noqa: F401
except Exception:  # pragma: no cover - repli minimal sans serveur
    class Canvas:  # type: ignore[no-redef]
        def __init__(self, *args, **kwargs):
            self.width = 640
            self.height = 400

        def __getattr__(self, name):
            def noop(*args, **kwargs):
                return self
            return noop

    def screen(*args, **kwargs):  # type: ignore[no-redef]
        return Canvas()

    def show_image(*args, **kwargs):
        return None

    def show_file(*args, **kwargs):
        return None

    def emit(event):
        return None
