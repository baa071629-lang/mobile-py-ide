"""Fenêtre plein écran rendue par le serveur graphique."""

from __future__ import annotations

from server import gfxserver
from .surface import Surface, display_surface

_surface: Surface | None = None
_caption = "Python"
_initialised = False
_background = "#000000"


class Info:
    def __init__(self):
        surface = get_surface()
        self.current_w = surface.width if surface else 640
        self.current_h = surface.height if surface else 480
        self.window_w = self.current_w
        self.window_h = self.current_h
        self.bitsize = 32
        self.depth = 32


def init():
    global _initialised
    _initialised = True


def get_init():
    return _initialised and _surface is not None


def quit():
    global _surface, _initialised
    if _surface is not None:
        gfxserver.SERVER.close()
    _surface = None
    _initialised = False


def set_mode(size=(640, 480), flags: int = 0, depth: int = 32, display: int = 0,
             vsync: int = 0):
    global _surface
    from . import FULLSCREEN, SCALED, NOFRAME, RESIZABLE

    width, height = int(size[0]), int(size[1])
    fullscreen = bool(flags & FULLSCREEN) or bool(flags & SCALED)
    _surface = display_surface(width, height)
    gfxserver.SERVER.open(
        width, height, _background,
        fullscreen=fullscreen, title=_caption, mode="pygame",
    )
    gfxserver.SERVER.present()
    return _surface


def get_surface():
    return _surface


def flip():
    gfxserver.SERVER.present()


def update(*args, **kwargs):
    gfxserver.SERVER.present()


def set_caption(title, icontitle=None):
    global _caption
    _caption = str(title or "")
    gfxserver.SERVER.set_title(_caption)


def get_caption():
    return (_caption, _caption)


def set_icon(icon):
    return None


def get_active():
    return True


def get_driver():
    return "pyide"


def list_modes(*args, **kwargs):
    return [(640, 480), (800, 480), (854, 480), (960, 540), (1280, 720)]


def toggle_fullscreen():
    surface = get_surface()
    if surface is None:
        return 0
    gfxserver.SERVER.set_fullscreen(not gfxserver.SERVER.fullscreen)
    return 0


def get_window_size():
    surface = get_surface()
    return (surface.width, surface.height) if surface else (0, 0)


def set_window_size(size):
    return None


def set_window_title(title):
    set_caption(title)


def get_window_surface():
    return get_surface()
