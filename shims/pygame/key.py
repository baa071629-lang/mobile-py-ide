"""État des touches (rempli par les événements de l'IDE)."""

from __future__ import annotations

from server import gfxserver

from .event import _key_name

_KEY_CODES = {
    "LEFT": 1073741904, "RIGHT": 1073741903, "UP": 1073741906, "DOWN": 1073741905,
    "SPACE": 32, "RETURN": 13, "ESCAPE": 27, "BACKSPACE": 8, "TAB": 9,
}
for _letter in "ABCDEFGHIJKLMNOPQRSTUVWXYZ":
    _KEY_CODES[_letter] = ord(_letter.lower())


def get_pressed():
    pressed = gfxserver.SERVER.keys
    state = [False] * 512
    for name, down in pressed.items():
        code = _key_name(name)
        if 0 <= code < 512:
            state[code] = down
    return _KeyState(state)


def get_mods():
    pressed = gfxserver.SERVER.keys
    mods = 0
    if pressed.get("LSHIFT") or pressed.get("SHIFT"):
        mods |= 0x0001
    if pressed.get("LCTRL") or pressed.get("CTRL"):
        mods |= 0x0040
    if pressed.get("LALT") or pressed.get("ALT"):
        mods |= 0x0100
    return mods


def set_repeat(*args, **kwargs):
    return None


def get_repeat():
    return (0, 0)


def name(keycode):
    for name_, code in _KEY_CODES.items():
        if code == keycode:
            return name_.lower()
    return ""


def key_code(name_):
    return _KEY_CODES.get(str(name_).upper(), 0)


class _KeyState:
    def __init__(self, state):
        self._state = state

    def __getitem__(self, index):
        return self._state[index]

    def __len__(self):
        return len(self._state)

    def __iter__(self):
        return iter(self._state)
