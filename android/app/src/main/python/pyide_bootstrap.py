"""Point d'entrée Python de l'application Android.

Le code partagé (dossier ``server``, ``pyide_gui``, ``pyide_native``) est livré
dans l'asset ``python-src.zip`` : Kotlin l'extrait au démarrage puis appelle
``prepare`` pour l'ajouter au chemin d'import et renvoyer le module du pont.
"""

from __future__ import annotations

import os
import sys

_module = None


def prepare(python_home: str):
    """Ajoute le code extrait au chemin d'import et renvoie ``pyide_native``."""
    global _module
    home = os.path.abspath(python_home)
    if not os.path.isdir(home):
        os.makedirs(home, exist_ok=True)
    if home not in sys.path:
        sys.path.insert(0, home)
    import pyide_native  # noqa: WPS433 - import volontairement tardif

    _module = pyide_native
    return pyide_native


def module():
    return _module
