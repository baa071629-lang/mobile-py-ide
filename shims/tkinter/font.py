"""Polices tkinter (nom + taille, rendues par le serveur graphique)."""

from __future__ import annotations


class Font:
    def __init__(self, root=None, font=None, **options):
        if isinstance(font, Font):
            self.family, self.size, self.weight = font.family, font.size, font.weight
        elif isinstance(font, (tuple, list)):
            self.family = str(font[0])
            self.size = int(font[1]) if len(font) > 1 else 14
            self.weight = "bold" if len(font) > 2 and str(font[2]) == "bold" else "normal"
        else:
            self.family = str((font or options.get("family") or "TkDefaultFont"))
            self.size = int(options.get("size") or 14)
            self.weight = str(options.get("weight") or "normal")

    def actual(self, key=None):
        values = {"family": self.family, "size": self.size, "weight": self.weight}
        return values.get(key, values) if key else values

    def configure(self, **options):
        if "size" in options:
            self.size = int(options["size"])
        if "weight" in options:
            self.weight = str(options["weight"])

    config = configure

    def measure(self, text):
        return int(len(str(text)) * self.size * 0.62)

    def metrics(self, key=None):
        values = {"ascent": int(self.size * 0.8), "descent": int(self.size * 0.25),
                  "linespace": int(self.size * 1.35)}
        return values.get(key, 0) if key else values

    def __repr__(self):
        return f"<Font {self.family} {self.size}>"
