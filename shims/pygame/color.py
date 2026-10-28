"""Couleurs : tuples, noms CSS et hexadécimaux."""

from __future__ import annotations

NAMED = {
    "black": (0, 0, 0), "white": (255, 255, 255), "red": (255, 0, 0),
    "green": (0, 128, 0), "blue": (0, 0, 255), "yellow": (255, 255, 0),
    "cyan": (0, 255, 255), "magenta": (255, 0, 255), "gray": (128, 128, 128),
    "grey": (128, 128, 128), "orange": (255, 165, 0), "purple": (128, 0, 128),
    "pink": (255, 192, 203), "brown": (165, 42, 42), "lime": (0, 255, 0),
    "navy": (0, 0, 128), "teal": (0, 128, 128), "silver": (192, 192, 192),
    "maroon": (128, 0, 0), "olive": (128, 128, 0), "gold": (255, 215, 0),
    "skyblue": (135, 206, 235), "darkgreen": (0, 100, 0),
}


def parse(color) -> tuple[int, int, int, int]:
    """Retourne (r, g, b, a) depuis n'importe quelle forme acceptée."""
    if isinstance(color, Color):
        return (color.r, color.g, color.b, color.a)
    if isinstance(color, str):
        text = color.strip().lower()
        if text.startswith("#"):
            digits = text[1:]
            if len(digits) in (3, 4):
                digits = "".join(ch * 2 for ch in digits)
            try:
                r = int(digits[0:2], 16)
                g = int(digits[2:4], 16)
                b = int(digits[4:6], 16)
                a = int(digits[6:8], 16) if len(digits) >= 8 else 255
                return (r, g, b, a)
            except ValueError:
                return (0, 0, 0, 255)
        if text.startswith("rgb"):
            inside = text[text.find("(") + 1:text.rfind(")")]
            parts = [p.strip() for p in inside.split(",")]
            values = [int(float(p.rstrip("%"))) for p in parts if p]
            while len(values) < 4:
                values.append(255)
            return tuple(values[:4])  # type: ignore[return-value]
        return (*NAMED.get(text, (0, 0, 0)), 255)
    if isinstance(color, (tuple, list)):
        values = list(color)
        if len(values) == 1:
            values = [values[0]] * 3
        while len(values) < 4:
            values.append(255)
        try:
            return (int(values[0]), int(values[1]), int(values[2]), int(values[3]))
        except (TypeError, ValueError):
            return (0, 0, 0, 255)
    if isinstance(color, int):
        return (color & 0xFF, (color >> 8) & 0xFF, (color >> 16) & 0xFF, 255)
    return (0, 0, 0, 255)


def css(color, alpha: float | None = None) -> str:
    r, g, b, a = parse(color)
    if alpha is not None:
        a = int(max(0, min(1, alpha)) * 255)
    if a >= 255:
        return f"#{r:02x}{g:02x}{b:02x}"
    return f"rgba({r},{g},{b},{a / 255:.3f})"


class Color:
    def __init__(self, *args):
        if len(args) == 1:
            r, g, b, a = parse(args[0])
        else:
            values = list(args) + [255] * (4 - len(args))
            r, g, b, a = (int(v) for v in values[:4])
        self.r, self.g, self.b, self.a = r, g, b, a

    def __iter__(self):
        return iter((self.r, self.g, self.b, self.a))

    def __getitem__(self, index):
        return (self.r, self.g, self.b, self.a)[index]

    def __repr__(self):
        return f"Color({self.r}, {self.g}, {self.b}, {self.a})"

    def __eq__(self, other):
        try:
            return parse(other) == (self.r, self.g, self.b, self.a)
        except Exception:
            return NotImplemented

    def __hash__(self):
        return hash((self.r, self.g, self.b, self.a))

    def __str__(self):
        return css(self)
