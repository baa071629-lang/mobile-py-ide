"""Transformations de surfaces (implémentées par le serveur graphique).

Chaque transformation enveloppe les opérations de la source dans un groupe
``push`` / ``transform`` / ``pop`` : le rendu (canevas du navigateur) applique
la matrice, ce qui permet rotation, retournement et mise à l'échelle réels
sans rastériser côté Python.
"""

from __future__ import annotations

import math

from .error import PygameError
from .surface import Surface

# groupes : opérations qui délimitent une matrice
_GROUP_MARKERS = ("push", "transform", "pop")


def _identity() -> dict:
    return {"op": "transform", "a": 1.0, "b": 0.0, "c": 0.0, "d": 1.0, "e": 0.0, "f": 0.0}


def _wrap(surface: Surface, target: Surface, matrix: dict | None) -> Surface:
    """Copie les opérations de `surface` dans `target`, sous une matrice."""
    target._ops = []
    if matrix is not None:
        target._ops.append({"op": "push"})
        target._ops.append(matrix)
    target._ops.extend(dict(op) for op in surface._ops)
    if matrix is not None:
        target._ops.append({"op": "pop"})
    return target


def _matrix(a: float, b: float, c: float, d: float, e: float, f: float) -> dict:
    return {"op": "transform", "a": a, "b": b, "c": c, "d": d, "e": e, "f": f}


def scale(surface, size, dest_surface=None):
    width, height = int(size[0]), int(size[1])
    target = dest_surface or Surface((width, height))
    target.width, target.height = max(width, 0), max(height, 0)
    if surface.width <= 0 or surface.height <= 0:
        target._ops = []
        return target
    return _wrap(surface, target, _matrix(width / surface.width, 0, 0,
                                         height / surface.height, 0, 0))


def smoothscale(surface, size, dest_surface=None):
    return scale(surface, size, dest_surface)


def scale_by(surface, factor, dest_surface=None):
    return scale(surface, (max(int(surface.width * factor), 1),
                           max(int(surface.height * factor), 1)), dest_surface)


def flip(surface, flip_x: bool, flip_y: bool, dest_surface=None):
    target = dest_surface or Surface((surface.width, surface.height))
    target.width, target.height = surface.width, surface.height
    a = -1.0 if flip_x else 1.0
    d = -1.0 if flip_y else 1.0
    e = float(surface.width) if flip_x else 0.0
    f = float(surface.height) if flip_y else 0.0
    if not flip_x and not flip_y:
        return _wrap(surface, target, None)
    return _wrap(surface, target, _matrix(a, 0.0, 0.0, d, e, f))


def rotate(surface, angle, dest_surface=None):
    """Rotation dans le sens trigonométrique (comme pygame)."""
    radians = math.radians(angle)
    cos, sin = math.cos(radians), math.sin(radians)
    # Arrondi avant `ceil` : cos(90°) vaut 6e-17, pas 0.
    width = int(math.ceil(round(abs(surface.width * cos) + abs(surface.height * sin), 6)))
    height = int(math.ceil(round(abs(surface.width * sin) + abs(surface.height * cos), 6)))
    target = dest_surface or Surface((max(width, 1), max(height, 1)))
    target.width, target.height = max(width, 1), max(height, 1)
    if not surface.width or not surface.height:
        target._ops = []
        return target
    # Le canevas a un axe Y descendant : une rotation « visuelle » antihoraire
    # correspond à la matrice (cos, -sin, sin, cos) autour du centre.
    cx, cy = target.width / 2.0, target.height / 2.0
    ox, oy = surface.width / 2.0, surface.height / 2.0
    a, b, c, d = cos, -sin, sin, cos
    e = cx - (a * ox + c * oy)
    f = cy - (b * ox + d * oy)
    return _wrap(surface, target, _matrix(a, b, c, d, e, f))


def rotozoom(surface, angle, scale_factor, dest_surface=None):
    rotated = rotate(surface, angle)
    return scale(rotated, (max(int(surface.width * scale_factor), 1),
                           max(int(surface.height * scale_factor), 1)), dest_surface)


def chop(surface, rect):
    return surface.subsurface(rect)


def laplacian(surface, dest_surface=None):
    raise PygameError("transform.laplacian n'est pas disponible")


def average_surfaces(surfaces, dest_surface=None, palette_colors: int = 1):
    return surfaces[0] if surfaces else Surface((1, 1))


def threshold(dest_surface, source_surface, threshold_value, set_behavior: int = 1):
    return dest_surface
