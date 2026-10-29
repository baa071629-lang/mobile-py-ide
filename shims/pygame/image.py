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


def _decode_color(value, default=(0, 0, 0, 255)):
    if value is None:
        return default
    if isinstance(value, str) and value.startswith("#"):
        text = value[1:]
        try:
            if len(text) == 6:
                return (int(text[0:2], 16), int(text[2:4], 16), int(text[4:6], 16), 255)
            if len(text) == 8:
                return (int(text[0:2], 16), int(text[2:4], 16),
                        int(text[4:6], 16), int(text[6:8], 16))
        except ValueError:
            return default
    if isinstance(value, (tuple, list)) and len(value) >= 3:
        alpha = int(value[3]) if len(value) > 3 else 255
        return (int(value[0]), int(value[1]), int(value[2]), alpha)
    return default


def _apply_matrix(matrix, x, y, width, height):
    """Applique une matrice affine (a,b,c,d,e,f) à une boîte."""
    a, b, c, d, e, f = matrix
    corners = [(x, y), (x + width, y), (x, y + height), (x + width, y + height)]
    moved = [(a * px + c * py + e, b * px + d * py + f) for px, py in corners]
    xs = [point[0] for point in moved]
    ys = [point[1] for point in moved]
    return min(xs), min(ys), max(xs), max(ys)


def render(surface) -> "object":
    """Rastérise les opérations d'une surface dans une image Pillow RGBA."""
    ResultImage = _pil()
    if ResultImage is None:
        raise PygameError("Pillow est nécessaire pour convertir une surface en image.")
    from PIL import ImageDraw  # noqa: WPS433

    width = max(int(surface.width), 1)
    height = max(int(surface.height), 1)
    picture = ResultImage.new("RGBA", (width, height), (0, 0, 0, 255))
    draw = ImageDraw.Draw(picture, "RGBA")

    stack: list[tuple[float, float, float, float, float, float]] = []
    matrix = (1.0, 0.0, 0.0, 1.0, 0.0, 0.0)

    def mapped(x, y):
        a, b, c, d, e, f = matrix
        return (a * x + c * y + e, b * x + d * y + f)

    def fill_of(op, default=(255, 255, 255, 255)):
        return _decode_color(op.get("color") or op.get("fill"), default)

    for op in surface._ops:
        name = op.get("op")
        if name == "push":
            stack.append(matrix)
            continue
        if name == "pop":
            matrix = stack.pop() if stack else (1.0, 0.0, 0.0, 1.0, 0.0, 0.0)
            continue
        if name == "transform":
            incoming = (float(op.get("a", 1)), float(op.get("b", 0)),
                        float(op.get("c", 0)), float(op.get("d", 1)),
                        float(op.get("e", 0)), float(op.get("f", 0)))
            a1, b1, c1, d1, e1, f1 = matrix
            a2, b2, c2, d2, e2, f2 = incoming
            matrix = (a1 * a2 + c1 * b2, b1 * a2 + d1 * b2,
                      a1 * c2 + c1 * d2, b1 * c2 + d1 * d2,
                      a1 * e2 + c1 * f2 + e1, b1 * e2 + d1 * f2 + f1)
            continue
        if name == "clear":
            color = _decode_color(op.get("color"), (0, 0, 0, 255))
            draw.rectangle([0, 0, width, height], fill=color)
            continue
        if name == "rect":
            box = _apply_matrix(matrix, op.get("x", 0), op.get("y", 0),
                                op.get("w", 0), op.get("h", 0))
            if op.get("fill"):
                draw.rectangle(box, fill=fill_of(op))
            else:
                draw.rectangle(box, outline=fill_of(op),
                               width=max(int(op.get("width") or 1), 1))
            continue
        if name in {"ellipse", "arc"}:
            box = _apply_matrix(matrix, op.get("x", 0), op.get("y", 0),
                                op.get("w", 0), op.get("h", 0))
            if name == "arc":
                draw.arc(box, start=float(op.get("start") or 0),
                         end=float(op.get("stop") or 360), fill=fill_of(op),
                         width=max(int(op.get("width") or 1), 1))
            elif op.get("fill"):
                draw.ellipse(box, fill=fill_of(op))
            else:
                draw.ellipse(box, outline=fill_of(op),
                             width=max(int(op.get("width") or 1), 1))
            continue
        if name == "circle":
            cx, cy = op.get("x", 0), op.get("y", 0)
            r = op.get("r", 0)
            box = _apply_matrix(matrix, cx - r, cy - r, r * 2, r * 2)
            if op.get("fill"):
                draw.ellipse(box, fill=fill_of(op))
            else:
                draw.ellipse(box, outline=fill_of(op),
                             width=max(int(op.get("width") or 1), 1))
            continue
        if name == "line":
            draw.line([mapped(op.get("x1", 0), op.get("y1", 0)),
                       mapped(op.get("x2", 0), op.get("y2", 0))],
                      fill=fill_of(op), width=max(int(op.get("width") or 1), 1))
            continue
        if name in {"lines", "polygon"}:
            raw = op.get("points") or []
            points = [mapped(px, py) for px, py in raw]
            if len(points) < 2:
                continue
            if name == "polygon" or op.get("closed"):
                if name == "polygon" and op.get("fill"):
                    draw.polygon(points, fill=fill_of(op))
                else:
                    draw.line(points + [points[0]], fill=fill_of(op),
                              width=max(int(op.get("width") or 1), 1))
            else:
                draw.line(points, fill=fill_of(op),
                          width=max(int(op.get("width") or 1), 1))
            continue
        if name == "pixel":
            x, y = mapped(op.get("x", 0), op.get("y", 0))
            draw.point((int(x), int(y)), fill=fill_of(op))
            continue
        if name == "text":
            size = int(op.get("size") or 14)
            try:
                from PIL import ImageFont  # noqa: WPS433
                font = ImageFont.load_default(size=size)
            except Exception:  # pragma: no cover - Pillow ancien
                font = None
            x, y = mapped(op.get("x", 0), op.get("y", 0))
            lines = str(op.get("value") or "").split("\n")
            for index, line in enumerate(lines):
                draw.text((x, y + index * size * 1.35), line, fill=fill_of(op), font=font)
            continue
        if name == "image" and op.get("data"):
            data = str(op["data"])
            payload = data.split(",", 1)[1] if data.startswith("data:") else data
            try:
                sticker = ResultImage.open(io.BytesIO(base64.b64decode(payload)))
            except Exception:
                continue
            sticker = sticker.convert("RGBA")
            box = _apply_matrix(matrix, op.get("x", 0), op.get("y", 0),
                                op.get("w") or sticker.width, op.get("h") or sticker.height)
            target_size = (max(int(box[2] - box[0]), 1), max(int(box[3] - box[1]), 1))
            picture.alpha_composite(sticker.resize(target_size),
                                    (max(int(box[0]), 0), max(int(box[1]), 0)))
            continue
    return picture


def save(surface, path, **kwargs):
    if _pil() is None:
        raise PygameError("Pillow est nécessaire pour enregistrer une image.")
    target = _resolve(path)
    picture = render(surface)
    options = {}
    suffix = target.suffix.lower()
    if "namehint" in kwargs and kwargs["namehint"]:
        suffix = Path(str(kwargs["namehint"])).suffix.lower() or suffix
    if suffix in {".jpg", ".jpeg"}:
        options["quality"] = int(kwargs.get("quality") or 92)
        picture = picture.convert("RGB")
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        picture.save(target, **options)
    except OSError as exc:
        raise PygameError(f"Enregistrement impossible : {exc}") from exc
    return None


def tostring(surface, format: str = "png", **kwargs) -> bytes:
    """Encode la surface en octets (comme pygame.image.tostring simplifié)."""
    if _pil() is None:
        raise PygameError("Pillow est nécessaire pour encoder une image.")
    buffer = io.BytesIO()
    render(surface).save(buffer, format=(format or "png").upper())
    return buffer.getvalue()


def get_extended():
    return True


def load_basic(path, **kwargs):
    return load(path, **kwargs)


def load_extended(path, **kwargs):
    return load(path, **kwargs)
