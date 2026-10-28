"""Chargement et sauvegarde d'images (Pillow si disponible)."""

from __future__ import annotations

import base64
import io
from pathlib import Path

from .error import PygameError
from .surface import Surface


def _pil():
    try:
        from PIL import Image  # noqa: WPS433 - dépendance optionnelle
        return Image
    except Exception:  # pragma: no cover - Pillow absent
        return None


def _resolve(path) -> Path:
    candidate = Path(path)
    if not candidate.is_absolute():
        import os
        candidate = Path(os.getcwd()) / candidate
    return candidate


def load(path, **kwargs):
    Image = _pil()
    target = _resolve(path)
    if Image is None:
        raise PygameError(
            "Le module Pillow est nécessaire pour ouvrir des images. "
            "Installe « pillow » depuis l'onglet Modules et paquets."
        )
    try:
        with Image.open(target) as picture:
            picture = picture.convert("RGBA")
            buffer = io.BytesIO()
            picture.save(buffer, format="PNG")
            payload = base64.b64encode(buffer.getvalue()).decode("ascii")
            size = picture.size
    except FileNotFoundError as exc:
        raise PygameError(f"Fichier introuvable : {target}") from exc
    except OSError as exc:
        raise PygameError(f"Image illisible : {exc}") from exc

    surface = Surface(size)
    surface._emit("image", x=0, y=0, w=size[0], h=size[1],
                  data=f"data:image/png;base64,{payload}")
    surface._source = str(target)  # type: ignore[attr-defined]
    return surface


def save(surface, path, **kwargs):
    Image = _pil()
    if Image is None:
        raise PygameError("Pillow est nécessaire pour enregistrer une image.")
    target = _resolve(path)
    picture = Image.new("RGBA", (surface.width, surface.height), (0, 0, 0, 0))
    try:
        picture.save(target)
    except OSError as exc:
        raise PygameError(f"Enregistrement impossible : {exc}") from exc
    return None


def get_extended():
    return True


def load_basic(path, **kwargs):
    return load(path, **kwargs)


def load_extended(path, **kwargs):
    return load(path, **kwargs)
