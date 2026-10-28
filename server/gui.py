"""Écran graphique : canevas dessinable + affichage d'images et de tracés.

Les programmes exécutés dans l'IDE peuvent dessiner sans dépendance native :

    from pyide_gui import screen
    s = screen()
    s.clear("#101020")
    s.circle(120, 120, 40, "#89b4fa")
    s.text(10, 20, "Bonjour", "#ffffff")
    s.present()

Les images produites par Pillow (``Image.show()``) et les tracés Matplotlib
(``pyplot.show()``) sont également envoyés à l'écran graphique.
"""

from __future__ import annotations

import base64
import io
import json
import threading
from pathlib import Path

_emitter = None
_lock = threading.Lock()


def set_emitter(callback) -> None:
    """Définit la fonction qui pousse les événements vers l'interface."""
    global _emitter
    _emitter = callback


def emit(event: dict) -> None:
    callback = _emitter
    if callback is None:
        return
    with _lock:
        try:
            callback(event)
        except Exception:
            pass


class Canvas:
    """Canevas de dessin en coordonnées logiques (redimensionné côté UI)."""

    def __init__(self, width: int = 640, height: int = 400, background: str = "#101018",
                 fullscreen: bool = True, title: str = ""):
        self.width = int(width)
        self.height = int(height)
        self.background = background
        self._ops: list[dict] = []
        emit({"type": "gfx", "op": "open", "width": self.width, "height": self.height,
              "background": self.background, "fullscreen": bool(fullscreen),
              "title": title or "pyide_gui", "mode": "canvas"})

    # -- primitives -----------------------------------------------------
    def clear(self, color: str | None = None) -> "Canvas":
        self.background = color or self.background
        self._ops = []
        emit({"type": "gfx", "op": "clear", "color": self.background})
        return self

    def rect(self, x, y, w, h, color="#ffffff", fill=True, width=1) -> "Canvas":
        self._op("rect", x=x, y=y, w=w, h=h, color=color, fill=bool(fill), width=int(width))

    def circle(self, x, y, r, color="#ffffff", fill=True, width=1) -> "Canvas":
        self._op("circle", x=x, y=y, r=r, color=color, fill=bool(fill), width=int(width))

    def line(self, x1, y1, x2, y2, color="#ffffff", width=1) -> "Canvas":
        self._op("line", x1=x1, y1=y1, x2=x2, y2=y2, color=color, width=int(width))

    def polygon(self, points, color="#ffffff", fill=True) -> "Canvas":
        self._op("polygon", points=[[float(px), float(py)] for px, py in points],
                 color=color, fill=bool(fill))

    def text(self, x, y, value, color="#ffffff", size=14) -> "Canvas":
        self._op("text", x=x, y=y, value=str(value), color=color, size=int(size))

    def pixel(self, x, y, color="#ffffff") -> "Canvas":
        self._op("pixel", x=x, y=y, color=color)

    def present(self) -> "Canvas":
        emit({"type": "gfx", "op": "present"})
        return self

    def clear_events(self):
        pass

    def _op(self, name: str, **payload) -> None:
        event = {"type": "gfx", "op": name}
        event.update(payload)
        self._ops.append(event)
        emit(event)

    # -- helpers façon pygame -------------------------------------------
    def blit_image(self, data: bytes, x: int = 0, y: int = 0) -> "Canvas":
        encoded = base64.b64encode(data).decode("ascii")
        self._op("image", x=x, y=y, data=encoded)
        return self


_default_canvas: Canvas | None = None


def screen(width: int = 640, height: int = 400, background: str = "#101018",
           fullscreen: bool = True, title: str = "") -> Canvas:
    global _default_canvas
    _default_canvas = Canvas(width, height, background, fullscreen=fullscreen, title=title)
    return _default_canvas


def show_image(data: bytes, title: str = "") -> None:
    emit({"type": "image", "title": title,
          "data": base64.b64encode(data).decode("ascii")})


def show_file(path: str | Path, title: str = "") -> None:
    try:
        show_image(Path(path).read_bytes(), title or Path(path).name)
    except OSError:
        pass


# ---------- accroches (Pillow, Matplotlib) ----------

def install_hooks() -> None:
    """Fait pointer ``plt.show()`` et ``Image.show()`` vers l'écran graphique."""
    try:
        import matplotlib

        matplotlib.use("Agg", force=True)
        import matplotlib.pyplot as plt

        def _plt_show(*_args, **_kwargs):
            buffer = io.BytesIO()
            plt.savefig(buffer, format="png", dpi=140, bbox_inches="tight")
            buffer.seek(0)
            show_image(buffer.read(), "Matplotlib")
            plt.close("all")

        plt.show = _plt_show
    except Exception:
        pass

    try:
        from PIL import Image

        def _image_show(self, title=None, **_kwargs):
            buffer = io.BytesIO()
            self.save(buffer, format="PNG")
            buffer.seek(0)
            show_image(buffer.read(), title or "Image")

        Image.Image.show = _image_show
    except Exception:
        pass


def canvas_from_json(payload: str) -> None:
    """Utilitaire de test : rejoue une liste d'opérations JSON."""
    for event in json.loads(payload):
        emit(event)


PYIDE_GUI_MODULE = True
