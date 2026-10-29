"""Polices : rendu de texte sur le canevas (sans dépendance native)."""

from __future__ import annotations

from .color import css
from .surface import Surface

_DEFAULT = "ui-sans-serif, system-ui, 'Segoe UI', Roboto, sans-serif"
_MONO = "ui-monospace, 'Cascadia Code', Menlo, monospace"


class Font:
    def __init__(self, name: str | None = None, size: int = 20, bold: bool = False,
                 italic: bool = False, **kwargs):
        self.name = name or _DEFAULT
        self.point_size = max(int(size), 6)
        self.bold = bool(bold)
        self.italic = bool(italic)
        self._family = _MONO if name and any(
            key in str(name).lower() for key in ("mono", "courier", "consol")
        ) else _DEFAULT

    def _metrics(self, text: str) -> tuple[int, int]:
        lines = str(text).split("\n")
        longest = max((len(part) for part in lines), default=0)
        ratio = 0.63 if self._family == _MONO else 0.58
        width = int(longest * self.point_size * ratio) + 2
        height = int(self.point_size * 1.35) * max(len(lines), 1)
        return max(width, 1), max(height, 1)

    # -- API pygame ------------------------------------------------------
    def size(self, text):
        return self._metrics(text)

    def get_height(self):
        return int(self.point_size * 1.35)

    def get_ascent(self):
        return int(self.point_size * 1.05)

    def get_descent(self):
        return int(self.point_size * 0.3)

    def get_linesize(self):
        return int(self.point_size * 1.4)

    def set_bold(self, value: bool):
        self.bold = bool(value)

    def set_italic(self, value: bool):
        self.italic = bool(value)

    def set_underline(self, value: bool):
        return None

    def render(self, text, antialias: bool = True, color=(255, 255, 255),
               background=None):
        width, height = self._metrics(text)
        surface = Surface((width, height))
        if background is not None:
            surface._emit("clear", color=css(background))
        surface._emit(
            "text", x=0, y=max(int(self.point_size * 0.15), 0), value=str(text),
            color=css(color), size=self.point_size, font=self._family,
            bold=self.bold, italic=self.italic, align="left",
        )
        return surface


_SYS_CACHE: dict[tuple, Font] = {}


def init():
    return None


def quit():
    return None


def get_init():
    return True


def get_default_font():
    return "sans"


def get_fonts():
    return ["sans", "monospace"]


def SysFont(name, size, bold: bool = False, italic: bool = False):
    if isinstance(name, (list, tuple)):
        name = name[0] if name else None
    key = (str(name), int(size), bool(bold), bool(italic))
    if key not in _SYS_CACHE:
        _SYS_CACHE[key] = Font(name, size, bold=bold, italic=italic)
    return _SYS_CACHE[key]


def match_font(name, bold: bool = False, italic: bool = False):
    return _MONO if "mono" in str(name).lower() else _DEFAULT
