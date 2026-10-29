"""Widgets Tk dessinés sur le serveur graphique de l'IDE."""

from __future__ import annotations

from . import Misc, _to_color

_FONT_SIZE = 14
_PAD = 6


def _font(size: int = _FONT_SIZE) -> str:
    return "ui-sans-serif, system-ui, 'Segoe UI', Roboto, sans-serif"


def layout_children(container, x: int, y: int, w: int, h: int) -> None:
    """Place les enfants (pack horizontal/vertical, grid, place)."""
    padding = _PAD
    cursor_y = y + padding
    cursor_x = x + padding
    row_height = 0
    grid_cells: dict[tuple[int, int], tuple] = {}
    for child in container.children:
        if getattr(child, "_destroyed", False):
            continue
        manager = child._layout.get("manager")
        if manager == "place":
            child._box = [x + int(child._layout.get("x", 0)),
                          y + int(child._layout.get("y", 0)),
                          int(child._layout.get("width") or 120),
                          int(child._layout.get("height") or 32)]
            continue
        if manager == "grid":
            row = int(child._layout.get("row", 0))
            column = int(child._layout.get("column", 0))
            span = int(child._layout.get("columnspan", 1))
            grid_cells[(row, column)] = (child, span)
            continue
        side = str(child._layout.get("side") or "top").lower()
        fill = str(child._layout.get("fill") or "").lower()
        padx = int(child._layout.get("padx") or 4) + 2
        pady = int(child._layout.get("pady") or 2) + 2
        natural_w, natural_h = child._natural_size()
        if side in {"top", "bottom"}:
            width = w - 2 * padx
            child._box = [x + padx, cursor_y, max(width, 40), natural_h]
            cursor_y += natural_h + 2 * pady
            row_height = 0
        else:  # left / right
            child._box = [cursor_x, y + pady, natural_w, max(h - 2 * pady, 28)]
            cursor_x += natural_w + 2 * padx
    if grid_cells:
        rows = max(row for row, _ in grid_cells) + 1
        columns = max(column for _, column in grid_cells) + 1
        cell_h = max(h // max(rows, 1), 30)
        cell_w = max(w // max(columns, 1), 80)
        for (row, column), (child, span) in grid_cells.items():
            child._box = [x + column * cell_w + padding,
                          y + row * cell_h + padding,
                          cell_w * span - 2 * padding,
                          cell_h - 2 * padding]


class Widget(Misc):
    def __init__(self, master=None, **options):
        super().__init__(master, **options)
        self._text = str(options.get("text", options.get("label", "")))
        self._options.setdefault("background", None)
        self._options.setdefault("foreground", "#111111")

    def _natural_size(self):
        width = self._layout.get("width") or 160
        height = self._layout.get("height")
        font_size = int(self._options.get("font_size") or _FONT_SIZE)
        lines = str(self._text).split("\n")
        text_width = max((len(line) for line in lines), default=0) * int(font_size * 0.62)
        needed = int(font_size * 1.6) * max(len(lines), 1) + 16
        return (int(width or max(text_width + 24, 60)), int(height or max(needed, 32)))

    def _bg(self, fallback="#e8e8e8"):
        return _to_color(self._options.get("background"), fallback)

    def _fg(self):
        return _to_color(self._options.get("foreground"), "#111111")

    def _font_options(self):
        size = int(self._options.get("font_size") or _FONT_SIZE)
        return {"size": size, "font": _font(size),
                "bold": str(self._options.get("font", "")).lower().endswith("bold")}


class Frame(Widget):
    def __init__(self, master=None, **options):
        super().__init__(master, **options)
        self._options.setdefault("background", None)

    def _draw(self, ops, x, y, w, h):
        background = _to_color(self._options.get("background"), "#dfe0e4")
        ops.append({"op": "rect", "x": x, "y": y, "w": w, "h": h,
                    "color": background, "fill": True, "width": 1})
        layout_children(self, x, y, w, h)

    def _handle(self, event, x, y, w, h):
        return False


class Label(Widget):
    def _natural_size(self):
        width = self._layout.get("width")
        size = int(self._options.get("font_size") or _FONT_SIZE)
        text = str(self._options.get("text", self._text))
        lines = text.split("\n")
        if self._options.get("wraplength"):
            text_width = int(self._options["wraplength"])
            height = size * 1.6 * max(len(lines), 1) + 10
        else:
            text_width = max((len(line) for line in lines), default=0) * int(size * 0.62) + 16
            height = size * 1.6 * max(len(lines), 1) + 10
        return (int(width or max(text_width, 40)), int(height))

    def _draw(self, ops, x, y, w, h):
        background = self._options.get("background")
        if background is not None:
            ops.append({"op": "rect", "x": x, "y": y, "w": w, "h": h,
                        "color": _to_color(background), "fill": True, "width": 1})
        text = str(self._options.get("text", self._text))
        size = int(self._options.get("font_size") or _FONT_SIZE)
        anchor = str(self._options.get("anchor") or "w").lower()
        px = x + 8 if anchor.startswith("w") else x + w / 2
        align = "left" if anchor.startswith("w") else "center"
        lines = text.split("\n")
        for index, line in enumerate(lines):
            ops.append({"op": "text", "x": px, "y": y + 6 + index * int(size * 1.45),
                        "value": line, "color": self._fg(), "size": size,
                        "font": _font(size), "align": align})


class Button(Widget):
    def __init__(self, master=None, **options):
        super().__init__(master, **options)
        self._command = options.get("command")
        self._pressed = False

    def invoke(self):
        if callable(self._command):
            try:
                self._command()
            except Exception:
                import traceback
                traceback.print_exc()

    def _natural_size(self):
        size = int(self._options.get("font_size") or _FONT_SIZE)
        text = str(self._options.get("text", self._text))
        width = self._layout.get("width") or max(len(text) * int(size * 0.62) + 28, 96)
        height = self._layout.get("height") or int(size * 2.3)
        return (int(width), int(height))

    def _draw(self, ops, x, y, w, h):
        active = self._pressed
        background = _to_color(self._options.get("background"), "#c9cdd6" if active else "#f2f3f5")
        border = _to_color(self._options.get("activebackground"), "#8ea0ff" if active else "#9aa0ad")
        ops.append({"op": "rect", "x": x, "y": y, "w": w, "h": h,
                    "color": background, "fill": True, "width": 1})
        ops.append({"op": "rect", "x": x, "y": y, "w": w, "h": h,
                    "color": border, "fill": False, "width": 2})
        size = int(self._options.get("font_size") or _FONT_SIZE)
        ops.append({"op": "text", "x": x + w / 2, "y": y + h / 2 - size * 0.65,
                    "value": str(self._options.get("text", self._text)),
                    "color": self._fg(), "size": size, "font": _font(size),
                    "align": "center"})

    def _handle(self, event, x, y, w, h):
        kind = event.get("type")
        ex, ey = int(event.get("x", 0)), int(event.get("y", 0))
        inside = x <= ex <= x + w and y <= ey <= y + h
        if kind == "mouse" and event.get("action") == "down" and inside:
            self._pressed = True
            return True
        if kind == "mouse" and event.get("action") == "up":
            was_pressed = self._pressed
            self._pressed = False
            if was_pressed and inside:
                self.invoke()
            return was_pressed
        return False


class Entry(Widget):
    def __init__(self, master=None, **options):
        super().__init__(master, **options)
        self._value = str(options.get("textvariable").get() if hasattr(
            options.get("textvariable"), "get") else options.get("text", ""))
        self._var = options.get("textvariable")
        self._focused = False

    def _natural_size(self):
        width = self._layout.get("width") or 200
        height = self._layout.get("height") or 36
        return (int(width), int(height))

    def get(self):
        return self._value

    def set(self, value):
        self._value = str(value)
        if self._var is not None:
            self._var.set(self._value)
        self.winfo_toplevel()._invalidate()

    def insert(self, index, text):
        self.set(self._value + str(text))

    def delete(self, first, last=None):
        if str(first) == "0" and str(last) in {"end", None}:
            self.set("")
        else:
            self.set("")

    def focus(self):
        self._focused = True
        self.winfo_toplevel()._focus = self
        self.winfo_toplevel()._invalidate()

    def _draw(self, ops, x, y, w, h):
        ops.append({"op": "rect", "x": x, "y": y, "w": w, "h": h,
                    "color": "#ffffff", "fill": True, "width": 1})
        ops.append({"op": "rect", "x": x, "y": y, "w": w, "h": h,
                    "color": "#4a90e2" if self._focused else "#9aa0ad",
                    "fill": False, "width": 2})
        size = int(self._options.get("font_size") or _FONT_SIZE)
        shown = self._value if self._options.get("show") is None else str(
            self._options.get("show")) * len(self._value)
        cursor = " |" if self._focused else ""
        ops.append({"op": "text", "x": x + 8, "y": y + h / 2 - size * 0.6,
                    "value": shown + cursor, "color": self._fg(), "size": size,
                    "font": _font(size), "align": "left"})

    def _handle(self, event, x, y, w, h):
        kind = event.get("type")
        ex, ey = int(event.get("x", 0)), int(event.get("y", 0))
        inside = x <= ex <= x + w and y <= ey <= y + h
        if kind == "mouse" and event.get("action") in {"down", "up"}:
            changed = self._focused != inside
            self._focused = inside
            if inside:
                self.winfo_toplevel()._focus = self
            return changed
        if kind == "key" and self._focused and event.get("down"):
            name = str(event.get("name", "")).upper()
            if name in {"BACKSPACE", "DELETE"}:
                self.set(self._value[:-1])
                return True
            if name in {"ENTER", "RETURN"}:
                handler = self._bindings.get("<Return>")
                if callable(handler):
                    handler(event)
                return True
            text = str(event.get("text", ""))
            if text and text.isprintable():
                self.set(self._value + text)
                return True
        return False


class Text(Widget):
    def __init__(self, master=None, **options):
        super().__init__(master, **options)
        self._value = ""
        self._focused = False

    def _natural_size(self):
        return (int(self._layout.get("width") or 260),
                int(self._layout.get("height") or 140))

    def get(self, first="1.0", last="end"):
        return self._value

    def insert(self, index, content):
        self._value += str(content)
        self.winfo_toplevel()._invalidate()

    def delete(self, first, last=None):
        self._value = ""
        self.winfo_toplevel()._invalidate()

    def see(self, index):
        return None

    def _draw(self, ops, x, y, w, h):
        ops.append({"op": "rect", "x": x, "y": y, "w": w, "h": h,
                    "color": "#ffffff", "fill": True, "width": 1})
        size = int(self._options.get("font_size") or _FONT_SIZE)
        lines = self._value.split("\n")[-max(int(h // (size * 1.45)), 1):]
        for index, line in enumerate(lines):
            ops.append({"op": "text", "x": x + 8, "y": y + 6 + index * int(size * 1.45),
                        "value": line, "color": self._fg(), "size": size,
                        "font": _font(size), "align": "left"})
        if self._focused:
            ops.append({"op": "rect", "x": x, "y": y, "w": w, "h": h,
                        "color": "#4a90e2", "fill": False, "width": 2})

    def _handle(self, event, x, y, w, h):
        if event.get("type") == "mouse" and event.get("action") == "down":
            self._focused = True
            self.winfo_toplevel()._focus = self
            return True
        if event.get("type") == "key" and event.get("down"):
            name = str(event.get("name", "")).upper()
            if name in {"ENTER", "RETURN"}:
                self.insert("end", "\n")
                return True
            if name == "BACKSPACE":
                self._value = self._value[:-1]
                self.winfo_toplevel()._invalidate()
                return True
            text = str(event.get("text", ""))
            if text and text.isprintable():
                self.insert("end", text)
                return True
        return False


class Checkbutton(Widget):
    def __init__(self, master=None, **options):
        super().__init__(master, **options)
        self._command = options.get("command")
        self._var = options.get("variable")
        self._checked = bool(self._var.get()) if hasattr(self._var, "get") else False

    def _natural_size(self):
        return (int(self._layout.get("width") or 220), int(self._layout.get("height") or 38))

    def _draw(self, ops, x, y, w, h):
        box = min(h - 10, 22)
        ops.append({"op": "rect", "x": x + 4, "y": y + (h - box) / 2, "w": box, "h": box,
                    "color": "#ffffff", "fill": True, "width": 1})
        ops.append({"op": "rect", "x": x + 4, "y": y + (h - box) / 2, "w": box, "h": box,
                    "color": "#4a90e2", "fill": False, "width": 2 if self._checked else 1})
        if self._checked:
            ops.append({"op": "line", "x1": x + 8, "y1": y + h / 2, "x2": x + box,
                        "y2": y + h / 2 + 6, "color": "#2f7d32", "width": 3})
        size = int(self._options.get("font_size") or _FONT_SIZE)
        ops.append({"op": "text", "x": x + box + 14, "y": y + h / 2 - size * 0.6,
                    "value": str(self._options.get("text", self._text)),
                    "color": self._fg(), "size": size, "font": _font(size),
                    "align": "left"})

    def _handle(self, event, x, y, w, h):
        if event.get("type") == "mouse" and event.get("action") == "up":
            self._checked = not self._checked
            if hasattr(self._var, "set"):
                self._var.set(self._checked)
            if callable(self._command):
                try:
                    self._command()
                except Exception:
                    import traceback
                    traceback.print_exc()
            return True
        return False


class Canvas(Widget):
    def __init__(self, master=None, **options):
        super().__init__(master, **options)
        self._items: list[dict] = []
        self._next_id = 1

    def _natural_size(self):
        return (int(self._layout.get("width") or 300),
                int(self._layout.get("height") or 200))

    # -- création d'objets ---------------------------------------------
    def _add(self, **item):
        item["id"] = self._next_id
        self._next_id += 1
        self._items.append(item)
        self.winfo_toplevel()._invalidate()
        return item["id"]

    def create_rectangle(self, x1, y1, x2, y2, **options):
        return self._add(kind="rect", x1=min(x1, x2), y1=min(y1, y2),
                         x2=max(x1, x2), y2=max(y1, y2),
                         fill=options.get("fill", ""), outline=options.get("outline", "#000000"),
                         width=int(options.get("width", 1) or 1))

    def create_oval(self, x1, y1, x2, y2, **options):
        return self._add(kind="oval", x1=min(x1, x2), y1=min(y1, y2),
                         x2=max(x1, x2), y2=max(y1, y2),
                         fill=options.get("fill", ""), outline=options.get("outline", "#000000"),
                         width=int(options.get("width", 1) or 1))

    def create_line(self, *coords, **options):
        points = [int(v) for v in coords]
        return self._add(kind="line", coords=points,
                         fill=options.get("fill", "#000000"),
                         width=int(options.get("width", 1) or 1))

    def create_polygon(self, *coords, **options):
        points = [int(v) for v in coords]
        return self._add(kind="polygon", coords=points,
                         fill=options.get("fill", ""), outline=options.get("outline", "#000000"))

    def create_text(self, x, y, **options):
        return self._add(kind="text", x=x, y=y, text=str(options.get("text", "")),
                         fill=options.get("fill", "#000000"),
                         size=int(options.get("size") or options.get("font_size") or _FONT_SIZE))

    def create_arc(self, x1, y1, x2, y2, **options):
        return self._add(kind="arc", x1=min(x1, x2), y1=min(y1, y2),
                         x2=max(x1, x2), y2=max(y1, y2),
                         start=float(options.get("start", 0)),
                         extent=float(options.get("extent", 90)),
                         fill=options.get("fill", ""), outline=options.get("outline", "#000000"))

    def create_image(self, x, y, **options):
        return self._add(kind="image", x=x, y=y, data=options.get("data"))

    def delete(self, *items):
        if not items or "all" in [str(item) for item in items]:
            self._items.clear()
        else:
            ids = {int(item) for item in items if str(item).isdigit()}
            self._items = [item for item in self._items if item["id"] not in ids]
        self.winfo_toplevel()._invalidate()

    def itemconfigure(self, item_id, **options):
        for item in self._items:
            if item["id"] == item_id:
                item.update(options)
        self.winfo_toplevel()._invalidate()

    itemconfig = itemconfigure

    def move(self, item_id, dx, dy):
        for item in self._items:
            if item["id"] != item_id:
                continue
            for key in ("x1", "x2", "x", "y", "y1", "y2"):
                if key in item and isinstance(item[key], (int, float)):
                    item[key] += dx if key.startswith("x") else dy
            if "coords" in item:
                points = item["coords"]
                for index in range(0, len(points), 2):
                    points[index] += dx
                    points[index + 1] += dy
        self.winfo_toplevel()._invalidate()

    def coords(self, item_id, *values):
        for item in self._items:
            if item["id"] != item_id:
                continue
            if "coords" in item and values:
                item["coords"] = [int(v) for v in values]
            elif values and len(values) >= 4:
                item["x1"], item["y1"], item["x2"], item["y2"] = (int(v) for v in values[:4])
        self.winfo_toplevel()._invalidate()

    def find_all(self):
        return [item["id"] for item in self._items]

    def bind(self, sequence=None, func=None, add=None):
        if sequence == "<Button-1>":
            return super().bind("<Button-1>", func, add)
        return super().bind(sequence, func, add)

    # -- rendu ---------------------------------------------------------
    def _draw(self, ops, x, y, w, h):
        background = _to_color(self._options.get("background"), "#ffffff")
        ops.append({"op": "rect", "x": x, "y": y, "w": w, "h": h,
                    "color": background, "fill": True, "width": 1})
        ops.append({"op": "rect", "x": x, "y": y, "w": w, "h": h,
                    "color": "#9aa0ad", "fill": False, "width": 1})
        for item in self._items:
            kind = item["kind"]
            if kind == "rect":
                self._emit_rect(ops, item, x, y)
            elif kind == "oval":
                self._emit_shape(ops, item, x, y, "ellipse")
            elif kind == "line":
                coords = item["coords"]
                for index in range(0, len(coords) - 2, 2):
                    ops.append({"op": "line", "x1": x + coords[index], "y1": y + coords[index + 1],
                                "x2": x + coords[index + 2], "y2": y + coords[index + 3],
                                "color": _to_color(item.get("fill"), "#000000"),
                                "width": item.get("width", 1)})
            elif kind == "polygon":
                coords = item["coords"]
                points = [[x + coords[i], y + coords[i + 1]] for i in range(0, len(coords) - 1, 2)]
                ops.append({"op": "polygon", "points": points,
                            "color": _to_color(item.get("fill") or item.get("outline"), "#000000"),
                            "fill": bool(item.get("fill"))})
            elif kind == "text":
                ops.append({"op": "text", "x": x + item["x"], "y": y + item["y"] - item["size"],
                            "value": item.get("text", ""),
                            "color": _to_color(item.get("fill"), "#000000"),
                            "size": item["size"], "font": _font(item["size"]), "align": "center"})
            elif kind == "arc":
                self._emit_shape(ops, item, x, y, "arc")
            elif kind == "image" and item.get("data"):
                ops.append({"op": "image", "x": x + item["x"], "y": y + item["y"],
                            "data": item["data"]})

    def _emit_rect(self, ops, item, ox, oy):
        fill = item.get("fill")
        if fill:
            ops.append({"op": "rect", "x": ox + item["x1"], "y": oy + item["y1"],
                        "w": item["x2"] - item["x1"], "h": item["y2"] - item["y1"],
                        "color": _to_color(fill), "fill": True, "width": 1})
        outline = item.get("outline")
        if outline:
            ops.append({"op": "rect", "x": ox + item["x1"], "y": oy + item["y1"],
                        "w": item["x2"] - item["x1"], "h": item["y2"] - item["y1"],
                        "color": _to_color(outline), "fill": False,
                        "width": item.get("width", 1)})

    def _emit_shape(self, ops, item, ox, oy, kind):
        fill = item.get("fill")
        record = {"op": kind, "x": ox + item["x1"], "y": oy + item["y1"],
                  "w": item["x2"] - item["x1"], "h": item["y2"] - item["y1"],
                  "color": _to_color(fill or item.get("outline"), "#000000"),
                  "fill": bool(fill), "width": item.get("width", 1)}
        if kind == "arc":
            record["start"] = item.get("start", 0)
            record["stop"] = item.get("start", 0) + item.get("extent", 90)
        ops.append(record)

    def _handle(self, event, x, y, w, h):
        if event.get("type") == "mouse" and event.get("action") == "down":
            handler = self._bindings.get("<Button-1>")
            if callable(handler):
                from . import _Event
                handler(_Event(event, self))
            return True
        return False


class Menu(Widget):
    def __init__(self, master=None, **options):
        super().__init__(master, **options)
        self._items: list[tuple] = []

    def add_command(self, label=None, command=None, **kwargs):
        self._items.append((label, command))

    def add_cascade(self, *args, **kwargs):
        return None

    def add_separator(self):
        return None

    def add_checkbutton(self, *args, **kwargs):
        return None

    def _draw(self, ops, x, y, w, h):
        return None

    def _natural_size(self):
        return (0, 0)


def _noop(*args, **kwargs):
    return None


class _MessageBox:
    def showinfo(self, title=None, message=None, **kwargs):
        print(f"[info] {title or ''} {message or ''}".strip())
        return "ok"

    def showwarning(self, title=None, message=None, **kwargs):
        print(f"[avertissement] {title or ''} {message or ''}".strip())
        return "ok"

    def showerror(self, title=None, message=None, **kwargs):
        print(f"[erreur] {title or ''} {message or ''}".strip(), file=__import__("sys").stderr)
        return "ok"

    def askyesno(self, title=None, message=None, **kwargs):
        print(f"[question] {title or ''} {message or ''} -> oui".strip())
        return True

    askokcancel = askyesno
    askretrycancel = askyesno

    def askstring(self, title=None, prompt=None, **kwargs):
        return kwargs.get("initialvalue", "")


messagebox = _MessageBox()


def root_default():
    from . import Tk  # noqa: F401  (compatibilité descendante)

    return None
