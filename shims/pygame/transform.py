"""Transformations de surfaces."""

from __future__ import annotations

from .error import PygameError
from .surface import Surface


def _scaled_ops(surface: Surface, sx: float, sy: float) -> list[dict]:
    scaled: list[dict] = []
    for op in surface._ops:
        moved = dict(op)
        name = moved.get("op")
        for key, factor in (("x", sx), ("y", sy), ("w", sx), ("h", sy), ("r", sx)):
            if key in moved and isinstance(moved[key], (int, float)):
                moved[key] = moved[key] * factor
        if name in {"line", "lines"}:
            for key, factor in (("x1", sx), ("x2", sx), ("y1", sy), ("y2", sy)):
                if key in moved:
                    moved[key] = moved[key] * factor
        if name == "points":
            pass
        if "points" in moved:
            moved["points"] = [[px * sx, py * sy] for px, py in moved["points"]]
        if "width" in moved and isinstance(moved["width"], (int, float)):
            moved["width"] = max(moved["width"] * min(sx, sy), 1)
        if name == "text" and "size" in moved:
            moved["size"] = moved["size"] * min(sx, sy)
        scaled.append(moved)
    return scaled


def scale(surface, size, dest_surface=None):
    width, height = int(size[0]), int(size[1])
    target = dest_surface or Surface((width, height))
    target.width, target.height = width, height
    if surface.width <= 0 or surface.height <= 0:
        return target
    sx = width / surface.width
    sy = height / surface.height
    target._ops = _scaled_ops(surface, sx, sy)
    return target


def smoothscale(surface, size, dest_surface=None):
    return scale(surface, size, dest_surface)


def scale_by(surface, factor, dest_surface=None):
    return scale(surface, (surface.width * factor, surface.height * factor), dest_surface)


def flip(surface, flip_x: bool, flip_y: bool, dest_surface=None):
    # Le retournement n'est pas traduit en opérations : on renvoie une copie.
    target = dest_surface or surface.copy()
    return target


def rotate(surface, angle, dest_surface=None):
    target = dest_surface or Surface(
        (max(surface.width, surface.height), max(surface.width, surface.height))
    )
    target._ops = [dict(op) for op in surface._ops]
    return target


def rotozoom(surface, angle, scale_factor, dest_surface=None):
    return rotate(surface, angle, dest_surface)


def chop(surface, rect):
    return surface.subsurface(rect)


def laplacian(surface, dest_surface=None):
    raise PygameError("transform.laplacian n'est pas disponible")


def average_surfaces(surfaces, dest_surface=None, palette_colors: int = 1):
    return surfaces[0] if surfaces else Surface((1, 1))


def threshold(dest_surface, source_surface, threshold_value, set_behavior: int = 1):
    return dest_surface
