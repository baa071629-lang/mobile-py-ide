"""Instrumentation des programmes lancés par l'IDE.

Quand un programme tourne depuis Mobile Py IDE (``PYIDE_IN_IDE=1``), on signale
à l'interface chaque lecture de l'entrée standard : le terminal peut alors
afficher son champ de saisie au bon moment, comme le terminal intégré de
PyramIDE.

Ce module est chargé automatiquement par Python grâce au ``PYTHONPATH`` que le
serveur ajoute (dossier de l'application). Il est totalement inactif hors IDE.
"""

from __future__ import annotations

import builtins
import json
import os
import sys

_EVENTS = os.environ.get("PYIDE_GFX_FILE", "").strip()
_ACTIVE = bool(os.environ.get("PYIDE_IN_IDE")) and bool(_EVENTS)
_installed = False


def _emit(event: dict) -> None:
    if not _ACTIVE:
        return
    try:
        with open(_EVENTS, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(event) + "\n")
    except OSError:
        pass


def install() -> None:
    global _installed
    if _installed or not _ACTIVE:
        return
    _installed = True

    original_input = builtins.input

    def input(prompt="") -> str:  # noqa: A001
        _emit({"type": "need_input"})
        return original_input(prompt)

    input.__doc__ = original_input.__doc__
    builtins.input = input

    stdin = sys.stdin
    if stdin is not None and hasattr(stdin, "readline"):
        original_readline = stdin.readline

        def readline(*args, **kwargs):
            _emit({"type": "need_input"})
            return original_readline(*args, **kwargs)

        try:
            stdin.readline = readline
        except (AttributeError, TypeError):
            pass


install()
