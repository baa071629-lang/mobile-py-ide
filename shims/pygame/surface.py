"""Surfaces pygame rendues par le serveur graphique de l'IDE."""

from __future__ import annotations

from server import gfxserver
from .color import css, parse
from .rect import Rect, rect_or_none

_TRANSLATED = {"rect", "circle", "ellipse", "line", "lines", "polygon", "arc", "text", "image"}
_GROUP_MARKERS = ("push", "transform", "pop")


def _has_group(ops) -> bool:
    return any(op.get("op") in _GROUP_MARKERS for op in ops)


def _translate(op: dict, dx: int, dy: int) -> dict:
    moved = dict(op)
    name = moved.get("op")
    if name not in _TRANSLATED:
        return moved
    if "x" in moved:
        moved["x"] = moved["x"] + dx
    if "y" in moved:
        moved["y"] = moved["y"] + dy
    if "x1" in moved:
        moved["x1"] = moved["x1"] + dx
        moved["y1"] = moved["y1"] + dy
        moved["x2"] = moved["x2"] + dx
        moved["y2"] = moved["y2"] + dy
    if "points" in moved:
        moved["points"] = [[px + dx, py + dy] for px, py in moved["points"]]
    return moved


class Surface:
    def __init__(self, size, flags: int = 0, depth: int = 32, masks=None):
        self.width, self.height = int(size[0]), int(size[1])
        self.flags = int(flags)
        self._ops: list[dict] = []
        self._display = False
        self._fill = (0, 0, 0, 0)
        self._alpha = 255
        self._colorkey = None
        self._clip = None
        self._pixels: dict[tuple[int, int], tuple] = {}

    # ---------- infrastructure ----------
    def _emit(self, name: str, **payload) -> None:
        if self._display:
            gfxserver.SERVER.op(name, **payload)
        else:
            record = {"op": name}
            record.update(payload)
            self._ops.append(record)

    def get_size(self):
        return (self.width, self.height)

    def get_width(self):
        return self.width

    def get_height(self):
        return self.height

    def get_rect(self, **kwargs):
        rect = Rect(0, 0, self.width, self.height)
        for key, value in kwargs.items():
            setattr(rect, key, value)
        return rect

    def get_flags(self):
        return self.flags

    def get_bitsize(self):
        return 32

    def get_pitch(self):
        return self.width * 4

    def get_bounding_rect(self):
        return Rect(0, 0, self.width, self.height)

    # ---------- dessin ----------
    def fill(self, color=(0, 0, 0), rect=None, special_flags: int = 0):
        area = rect_or_none(rect)
        if area is None:
            self._fill = parse(color)
            self._emit("clear", color=css(color))
            return Rect(0, 0, self.width, self.height)
        self._emit("rect", x=area.x, y=area.y, w=area.width, h=area.height,
                   color=css(color), fill=True, width=1)
        return area

    def blit(self, source, dest, area=None, special_flags: int = 0):
        if dest is None:
            return Rect(0, 0, 0, 0)
        if hasattr(dest, "x"):
            dx, dy = dest.x, dest.y
        else:
            dx, dy = int(dest[0]), int(dest[1])
        source_ops = list(getattr(source, "_ops", []))
        if not source_ops:
            source_ops = [{"op": "rect", "x": 0, "y": 0, "w": getattr(source, "width", 0),
                           "h": getattr(source, "height", 0),
                           "color": css(getattr(source, "_fill", (0, 0, 0, 0))), "fill": True}]
        if _has_group(source_ops):
            # La source contient des matrices : on translate le groupe entier
            # au lieu de déplacer chaque primitive (sinon les rotations cassent).
            self._emit("push")
            self._emit("transform", a=1.0, b=0.0, c=0.0, d=1.0, e=float(dx), f=float(dy))
            for op in source_ops:
                record = dict(op)
                name = record.pop("op")
                self._emit(name, **record)
            self._emit("pop")
            return Rect(dx, dy, getattr(source, "width", 0), getattr(source, "height", 0))
        for op in source_ops:
            moved = _translate(op, dx, dy)
            name = moved.pop("op")
            self._emit(name, **moved)
        return Rect(dx, dy, getattr(source, "width", 0), getattr(source, "height", 0))

    def blits(self, sequence, doreturn: bool = True):
        rects = [self.blit(source, dest) for source, dest in sequence]
        return rects if doreturn else None

    def copy(self):
        clone = Surface((self.width, self.height), self.flags)
        clone._ops = [dict(op) for op in self._ops]
        clone._fill = self._fill
        return clone

    def subsurface(self, rect):
        area = Rect(rect)
        clone = Surface((max(area.width, 0), max(area.height, 0)), self.flags)
        if _has_group(self._ops):
            clone._ops = ([{"op": "push"},
                           {"op": "transform", "a": 1.0, "b": 0.0, "c": 0.0, "d": 1.0,
                            "e": float(-area.x), "f": float(-area.y)}]
                          + [dict(op) for op in self._ops]
                          + [{"op": "pop"}])
            return clone
        for op in self._ops:
            moved = _translate(op, -area.x, -area.y)
            clone._ops.append(moved)
        return clone

    def set_at(self, position, color):
        x, y = int(position[0]), int(position[1])
        if 0 <= x < self.width and 0 <= y < self.height:
            self._pixels[(x, y)] = parse(color)
            self._emit("pixel", x=x, y=y, color=css(color))

    def get_at(self, position):
        x, y = int(position[0]), int(position[1])
        return self._pixels.get((x, y), self._fill)

    def convert(self, *args, **kwargs):
        return self

    def convert_alpha(self, *args, **kwargs):
        return self

    def set_alpha(self, value, flags: int = 0):
        self._alpha = int(value)

    def get_alpha(self):
        return self._alpha

    def set_colorkey(self, color, flags: int = 0):
        self._colorkey = color

    def get_colorkey(self):
        return self._colorkey

    def lock(self):
        return None

    def unlock(self):
        return None

    def set_clip(self, rect=None):
        self._clip = rect_or_none(rect)

    def get_clip(self):
        return self._clip or Rect(0, 0, self.width, self.height)

    def scroll(self, dx: int = 0, dy: int = 0):
        return None

    def __repr__(self):
        return f"<Surface({self.width}x{self.height})>"


def display_surface(width: int, height: int) -> Surface:
    surface = Surface((width, height))
    surface._display = True
    return surface
