"""Module `tkinter` fourni par Mobile Py IDE.

Les fenêtres et widgets sont dessinés par le **serveur graphique** de l'IDE
(plein écran, tactile) : `mainloop()` ouvre l'écran, rend les widgets et
distribue les touchers aux callbacks (`command`, `bind("<Button-1>")`).

Sous-ensemble couvert : `Tk`, `Toplevel`, `Frame`, `Label`, `Button`, `Entry`,
`Text`, `Canvas`, `Checkbutton`, les gestionnaires `pack`/`grid`/`place`,
`after`, `update`, `mainloop`, `StringVar`/`IntVar`/`BooleanVar`, `messagebox`.
Ce n'est pas le Tk de CPython : certaines options rares sont ignorées.
"""

from __future__ import annotations

import time as _time

from server import gfxserver


def _now_ms() -> int:
    return int(_time.monotonic() * 1000)


class Variable:
    def __init__(self, master=None, value=None, name=None):
        self._value = value
        self._trace: list = []

    def get(self):
        return self._value

    def set(self, value):
        self._value = value
        for callback in list(self._trace):
            try:
                callback()
            except Exception:
                pass

    def trace_add(self, mode, callback):
        self._trace.append(callback)
        return "trace"

    def trace(self, mode, callback):
        return self.trace_add(mode, callback)

    def trace_remove(self, *args):
        return None


class StringVar(Variable):
    def __init__(self, master=None, value="", name=None):
        super().__init__(master, "" if value is None else str(value), name)

    def set(self, value):
        super().set("" if value is None else str(value))


class IntVar(Variable):
    def __init__(self, master=None, value=0, name=None):
        super().__init__(master, int(value or 0), name)

    def set(self, value):
        try:
            super().set(int(value))
        except (TypeError, ValueError):
            super().set(0)


class DoubleVar(Variable):
    def __init__(self, master=None, value=0.0, name=None):
        super().__init__(master, float(value or 0.0), name)


class BooleanVar(Variable):
    def __init__(self, master=None, value=False, name=None):
        super().__init__(master, bool(value), name)


def _to_color(value, default="#ececec"):
    if value is None:
        return default
    text = str(value).strip()
    if not text:
        return default
    if text.startswith("#") or text.startswith("rgb"):
        return text
    palette = {
        "white": "#ffffff", "black": "#000000", "gray": "#808080", "grey": "#808080",
        "red": "#d9534f", "green": "#5cb85c", "blue": "#337ab7",
        "lightgray": "#d3d3d3", "lightgrey": "#d3d3d3", "yellow": "#ffe066",
        "orange": "#f0ad4e", "pink": "#ffb6c1", "cyan": "#5bc0de",
        "light blue": "#add8e6", "lightblue": "#add8e6", "darkblue": "#00008b",
        "navy": "#000080", "purple": "#800080", "brown": "#8b4513",
    }
    return palette.get(text.lower(), text if text.startswith(("#", "rgb")) else default)


class Misc:
    """Base commune : options, géométrie, événements."""

    _counter = 0

    def __init__(self, master=None, **options):
        Misc._counter += 1
        self._id = Misc._counter
        self.master = master
        self.children: list = []
        self._options: dict = {"background": None, "foreground": "#000000"}
        self._layout: dict = {"manager": "pack", "side": "top", "fill": None,
                              "padx": 0, "pady": 0, "row": 0, "column": 0,
                              "columnspan": 1, "rowspan": 1, "sticky": "",
                              "x": 0, "y": 0, "width": None, "height": None}
        self._bindings: dict = {}
        self._destroyed = False
        self._box = [0, 0, 0, 0]
        self._text = ""
        if master is not None and hasattr(master, "children"):
            master.children.append(self)
        self.configure(**options)

    # -- options --------------------------------------------------------
    def configure(self, **options):
        for key, value in options.items():
            if key in {"width"} and value:
                self._layout["width"] = int(value)
            elif key in {"height"} and value:
                self._layout["height"] = int(value)
            else:
                self._options[key] = value
        if hasattr(self.master, "_invalidate"):
            self.master._invalidate()
        return None

    config = configure

    def cget(self, key):
        return self._options.get(key, "")

    def __getitem__(self, key):
        return self.cget(key)

    def __setitem__(self, key, value):
        self.configure(**{key: value})

    # -- gestionnaires de géométrie -------------------------------------
    def pack(self, **kwargs):
        self._layout.update({"manager": "pack", **kwargs})
        self.master._invalidate() if hasattr(self.master, "_invalidate") else None
        return self

    def grid(self, **kwargs):
        self._layout.update({"manager": "grid", **kwargs})
        if hasattr(self.master, "_invalidate"):
            self.master._invalidate()
        return self

    def place(self, **kwargs):
        self._layout.update({"manager": "place", **kwargs})
        if hasattr(self.master, "_invalidate"):
            self.master._invalidate()
        return self

    pack_forget = lambda self: None
    grid_forget = lambda self: None

    def grid_columnconfigure(self, *args, **kwargs):
        return None

    def grid_rowconfigure(self, *args, **kwargs):
        return None

    def columnconfigure(self, *args, **kwargs):
        return None

    def rowconfigure(self, *args, **kwargs):
        return None

    # -- événements -----------------------------------------------------
    def bind(self, sequence=None, func=None, add=None):
        if sequence is None:
            return list(self._bindings)
        if func is None:
            return self._bindings.get(sequence)
        self._bindings[sequence] = func
        return None

    def unbind(self, sequence):
        self._bindings.pop(sequence, None)

    def after(self, milliseconds, func=None, *args):
        root = self.winfo_toplevel()
        return root._schedule(int(milliseconds or 0), func, args)

    def after_idle(self, func, *args):
        return self.after(0, func, *args)

    def after_cancel(self, identifier):
        return None

    def focus_set(self):
        root = self.winfo_toplevel()
        root._focus = self
        root._invalidate()
        return None

    focus = focus_set

    def destroy(self):
        self._destroyed = True

    def winfo_toplevel(self):
        widget = self
        while getattr(widget, "master", None) is not None:
            widget = widget.master
        return widget

    def winfo_width(self):
        return self._box[2]

    def winfo_height(self):
        return self._box[3]

    def winfo_x(self):
        return self._box[0]

    def winfo_y(self):
        return self._box[1]

    def winfo_rootx(self):
        return self._box[0]

    def winfo_rooty(self):
        return self._box[1]

    def winfo_exists(self):
        return not self._destroyed

    def winfo_children(self):
        return list(self.children)

    def winfo_screenwidth(self):
        return self.winfo_toplevel()._width

    def winfo_screenheight(self):
        return self.winfo_toplevel()._height

    def update(self):
        self.winfo_toplevel()._render(force=True)

    def update_idletasks(self):
        return None

    # -- rendu ----------------------------------------------------------
    def _measure(self, width, height):
        return (self._layout.get("width") or width, self._layout.get("height") or height)

    def _draw(self, ops: list, x: int, y: int, w: int, h: int):
        background = _to_color(self._options.get("background"))
        if self._options.get("background") is not None:
            ops.append({"op": "rect", "x": x, "y": y, "w": w, "h": h,
                        "color": background, "fill": True, "width": 1})

    def _handle(self, event: dict, x: int, y: int, w: int, h: int) -> bool:
        return False


class Tk(Misc):
    def __init__(self, screenName=None, baseName=None, className="Tk", useTk=True, **options):
        super().__init__(None)
        self._width = int(options.get("width") or 0) or 420
        self._height = int(options.get("height") or 0) or 640
        self._title = "Tk"
        self._background = "#ececec"
        self._focus: Misc | None = None
        self._jobs: list = []
        self._dirty = True
        self._running = False
        self._quit = False
        self._gfx_open = False

    # -- fenêtre --------------------------------------------------------
    def geometry(self, spec=None):
        if spec is None:
            return f"{self._width}x{self._height}"
        text = str(spec)
        if "x" in text:
            size, _, position = text.partition("+")
            width, _, height = size.partition("x")
            try:
                self._width = int(width)
                self._height = int(height)
            except ValueError:
                pass
        self._invalidate()
        return None

    def title(self, value=None):
        if value is None:
            return self._title
        self._title = str(value)
        if self._gfx_open:
            gfxserver.SERVER.set_title(self._title)
        return None

    def configure(self, **options):
        if "background" in options or "bg" in options:
            self._background = _to_color(options.get("background") or options.get("bg"))
        super().configure(**options)

    config = configure

    def resizable(self, *args):
        return None

    def protocol(self, name, func=None):
        if name == "WM_DELETE_WINDOW" and func is not None:
            self._bindings["<Destroy>"] = lambda event: func()
        return None

    def iconify(self):
        return None

    def deiconify(self):
        return None

    def state(self, value=None):
        return "normal" if value is None else None

    def attributes(self, *args, **kwargs):
        return None

    def lift(self):
        return None

    def clip_type(self):
        return None

    def _invalidate(self):
        self._dirty = True

    def _schedule(self, delay_ms: int, func, args=()):
        when = _time.monotonic() + max(delay_ms, 0) / 1000
        self._jobs.append((when, func, args))
        return len(self._jobs)

    # -- boucle ---------------------------------------------------------
    def mainloop(self, n: int = 0):
        server = gfxserver.SERVER
        background = _to_color(self._background)
        server.open(self._width, self._height, background, fullscreen=True,
                    title=self._title, mode="tkinter")
        self._gfx_open = True
        self._running = True
        try:
            self._render(force=True)
            while not self._quit:
                self._run_jobs()
                events = server.poll()
                for event in events:
                    if event.get("type") == "quit":
                        self._quit = True
                        break
                    self._dispatch(event)
                if self._dirty:
                    self._render()
                _time.sleep(0.012)
        finally:
            self._running = False
            if self._gfx_open:
                server.close()
                self._gfx_open = False
        return None

    def _run_jobs(self):
        now = _time.monotonic()
        ready = [job for job in self._jobs if job[0] <= now]
        self._jobs = [job for job in self._jobs if job[0] > now]
        for _, func, args in ready:
            if func is None:
                continue
            try:
                func(*args)
            except Exception:
                import traceback
                traceback.print_exc()

    def quit_(self):
        self._quit = True

    def destroy(self):
        self._quit = True
        self._destroyed = True

    def _dispatch(self, event: dict):
        if event.get("type") == "resize":
            self._width = int(event.get("width") or self._width)
            self._height = int(event.get("height") or self._height)
            self._invalidate()
            return
        target = self._hit(event)
        if target is None:
            return
        for widget in (target, self):
            handlers = widget._bindings if widget is not target else target._bindings
            if not handlers:
                continue
            for sequence, callback in handlers.items():
                if self._matches(sequence, event):
                    try:
                        callback(_Event(event, target))
                    except Exception:
                        import traceback
                        traceback.print_exc()
        if target._handle(event, *target._box):
            self._invalidate()

    @staticmethod
    def _matches(sequence: str, event: dict) -> bool:
        kind = event.get("type")
        if sequence in {"<Button-1>", "<ButtonPress-1>"}:
            return kind == "mouse" and event.get("action") == "down" and event.get("button", 1) == 1
        if sequence == "<ButtonRelease-1>":
            return kind == "mouse" and event.get("action") == "up"
        if sequence == "<Motion>":
            return kind == "mouse" and event.get("action") == "move"
        if sequence == "<Key>":
            return kind == "key" and event.get("down")
        if sequence in {"<Return>", "<Key-Return>"}:
            return kind == "key" and event.get("down") and str(event.get("name", "")).upper() in {"ENTER", "RETURN"}
        if sequence == "<Escape>":
            return kind == "key" and event.get("down") and str(event.get("name", "")).upper() in {"ESCAPE", "ESC"}
        return False

    def _hit(self, event: dict):
        if event.get("type") != "mouse":
            return self._focus or self
        x, y = int(event.get("x", 0)), int(event.get("y", 0))
        return self._hit_tree(self, x, y) or self

    def _hit_tree(self, widget, x: int, y: int):
        for child in reversed(widget.children):
            found = self._hit_tree(child, x, y)
            if found is not None:
                return found
        bx, by, bw, bh = widget._box
        if widget is not self and bx <= x <= bx + bw and by <= y <= by + bh:
            return widget
        return None

    # -- rendu ----------------------------------------------------------
    def _render(self, force: bool = False):
        from ._widgets import layout_children

        ops: list[dict] = []
        ops.append({"op": "clear", "color": _to_color(self._background)})
        layout_children(self, 0, 0, self._width, self._height)
        for child in self.children:
            if not child._destroyed:
                child._draw(ops, *child._box)
        for op in ops:
            name = op.pop("op")
            gfxserver.SERVER.op(name, **op)
        gfxserver.SERVER.present()
        self._dirty = False

    def _measure(self, width, height):
        return (self._layout.get("width") or width, self._layout.get("height") or height)


class _Event:
    def __init__(self, raw: dict, widget):
        self.raw = raw
        self.widget = widget
        self.type = raw.get("type")
        self.x = int(raw.get("x", 0))
        self.y = int(raw.get("y", 0))
        self.x_root = self.x
        self.y_root = self.y
        self.num = int(raw.get("button", 1))
        self.keysym = str(raw.get("name", ""))
        self.char = str(raw.get("text", ""))
        self.width = int(raw.get("width", 0))
        self.height = int(raw.get("height", 0))

    def __repr__(self):
        return f"<Event {self.type} at {self.x},{self.y}>"


Toplevel = Tk


def mainloop(n: int = 0):
    from ._widgets import root_default

    root = root_default()
    if root is not None:
        root.mainloop(n)


from ._widgets import (  # noqa: E402  (après la définition de Tk/Misc)
    Button, Canvas, Checkbutton, Entry, Frame, Label, Menu, Text, messagebox,
)

Widget = Misc

__all__ = [
    "Tk", "Toplevel", "Frame", "Label", "Button", "Entry", "Text", "Canvas",
    "Checkbutton", "Menu", "Widget", "StringVar", "IntVar", "DoubleVar",
    "BooleanVar", "messagebox", "mainloop",
]
