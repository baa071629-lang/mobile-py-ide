"""Module `pygame` fourni par Mobile Py IDE.

Ce n'est pas SDL : les primitives sont envoyées au **serveur graphique** de
l'IDE, qui les dessine sur un canevas **plein écran**, et les touchers/clavier
reviennent dans la file d'événements. Le sous-ensemble couvre les programmes
classiques (boucle d'événements, dessin, texte, sprites, images, horloge).

Un vrai `pygame` installé (pip) a la priorité : ce module n'est ajouté qu'en
dernier recours dans `sys.path`.
"""

from __future__ import annotations

from . import display, draw, event, font, image, key, mixer, mouse, sprite, time, transform
from .color import Color
from .error import PygameError, error
from .rect import Rect
from .surface import Surface

# -- constantes ---------------------------------------------------------
QUIT = event.QUIT
KEYDOWN = event.KEYDOWN
KEYUP = event.KEYUP
MOUSEMOTION = event.MOUSEMOTION
MOUSEBUTTONDOWN = event.MOUSEBUTTONDOWN
MOUSEBUTTONUP = event.MOUSEBUTTONUP
MOUSEWHEEL = event.MOUSEWHEEL
VIDEORESIZE = event.VIDEORESIZE
FINGERDOWN = event.FINGERDOWN
FINGERUP = event.FINGERUP
FINGERMOTION = event.FINGERMOTION

FULLSCREEN = 0x80000000
DOUBLEBUF = 0x40000000
HWSURFACE = 0x00000001
OPENGL = 0x00000002
RESIZABLE = 0x00000010
NOFRAME = 0x00000020
SCALED = 0x00000200
SRCALPHA = 0x00010000
SRCCOLORKEY = 0x00001000
RLEACCEL = 0x00004000
BLEND_ADD = 1
BLEND_SUB = 2
BLEND_MULT = 3

HAS_ALPHA = True
K_LEFT = 1073741904
K_RIGHT = 1073741903
K_UP = 1073741906
K_DOWN = 1073741905
K_SPACE = 32
K_RETURN = 13
K_ESCAPE = 27
K_TAB = 9
K_BACKSPACE = 8
K_LSHIFT = 1073742049
K_LCTRL = 1073742048
KMOD_LSHIFT = 0x0001
KMOD_LCTRL = 0x0040

version = (2, 1, 0)
VERSION = "2.1.0-pyide"
vernum = 20210
IS_PYIDE_SHIM = True

_init = False
_error = ""


class Vector2:
    """Vecteur 2D minimal (utilisé par beaucoup d'exemples pygame)."""

    def __init__(self, x=0.0, y=None):
        if y is None:
            if hasattr(x, "__len__"):
                x, y = x[0], x[1]
            else:
                y = x
        self.x = float(x)
        self.y = float(y)

    def __add__(self, other):
        other = Vector2(other)
        return Vector2(self.x + other.x, self.y + other.y)

    def __sub__(self, other):
        other = Vector2(other)
        return Vector2(self.x - other.x, self.y - other.y)

    def __mul__(self, other):
        if isinstance(other, (int, float)):
            return Vector2(self.x * other, self.y * other)
        other = Vector2(other)
        return Vector2(self.x * other.x, self.y * other.y)

    __rmul__ = __mul__

    def __truediv__(self, other):
        return Vector2(self.x / other, self.y / other)

    def __iter__(self):
        return iter((self.x, self.y))

    def __getitem__(self, index):
        return (self.x, self.y)[index]

    def __len__(self):
        return 2

    def __repr__(self):
        return f"Vector2({self.x}, {self.y})"

    def length(self):
        return (self.x ** 2 + self.y ** 2) ** 0.5

    def normalize(self):
        length = self.length() or 1.0
        self.x /= length
        self.y /= length

    def as_tuple(self):
        return (self.x, self.y)


def init():
    global _init
    display.init()
    font.init()
    _init = True
    return (_init, 0)


def quit():  # noqa: A001 - API pygame
    global _init
    display.quit()
    _init = False


def get_init():
    return _init


def get_error():
    return _error


def set_error(message):
    global _error
    _error = str(message)


def register_quit(function):
    return None


def get_sdl_version():
    return (2, 0, 0)


def get_sdl_byteorder():
    return 1234


__all__ = [
    "Color", "Rect", "Surface", "Vector2", "display", "draw", "event", "font",
    "image", "key", "mixer", "mouse", "sprite", "time", "transform", "init",
    "quit", "get_init", "error", "PygameError",
]
