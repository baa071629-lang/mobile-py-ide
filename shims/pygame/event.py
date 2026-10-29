"""File d'événements alimentée par les touchers et le clavier de l'IDE."""

from __future__ import annotations

from server import gfxserver

QUIT = 256
ACTIVEEVENT = 1
KEYDOWN = 768
KEYUP = 769
MOUSEMOTION = 1024
MOUSEBUTTONDOWN = 1025
MOUSEBUTTONUP = 1026
MOUSEWHEEL = 1027
VIDEORESIZE = 32783
VIDEOEXPOSE = 32784
WINDOWEVENT = 32785
FINGERDOWN = 32768
FINGERUP = 32769
FINGERMOTION = 32770

_KEYMAP = {
    "ARROWLEFT": "LEFT", "ARROWRIGHT": "RIGHT", "ARROWUP": "UP", "ARROWDOWN": "DOWN",
    " ": "SPACE", "SPACEBAR": "SPACE", "ENTER": "RETURN", "RETURN": "RETURN",
    "ESC": "ESCAPE", "ESCAPE": "ESCAPE", "BACKSPACE": "BACKSPACE",
    "TAB": "TAB", "DELETE": "DELETE", "SHIFT": "LSHIFT", "CONTROL": "LCTRL",
    "CTRL": "LCTRL", "ALT": "LALT", "META": "LMETA",
}


class Event:
    def __init__(self, type: int, **attributes):  # noqa: A002 - API pygame
        self.type = type
        self.dict = {"type": type, **attributes}
        for key, value in attributes.items():
            setattr(self, key, value)

    def __repr__(self):
        return f"<Event({self.type} {self.dict})>"

    def __getitem__(self, key):
        if isinstance(key, int):
            return (self.type, self.dict)[key]
        if isinstance(key, slice):
            return (self.type, self.dict)[key]
        return self.dict[key]

    def __len__(self):
        return 2

    def __iter__(self):
        return iter((self.type, self.dict))


_pending: list[Event] = []


def _key_name(raw: str) -> int:
    name = _KEYMAP.get(str(raw).upper(), str(raw).upper())
    if len(name) == 1:
        return ord(name)
    return _KEY_CODES.get(name, 0)


_KEY_CODES = {
    "LEFT": 1073741904, "RIGHT": 1073741903, "UP": 1073741906, "DOWN": 1073741905,
    "SPACE": 32, "RETURN": 13, "ESCAPE": 27, "BACKSPACE": 8, "TAB": 9,
    "DELETE": 127, "LSHIFT": 1073742049, "LCTRL": 1073742048, "LALT": 1073742050,
    "LMETA": 1073742051, "A": 97, "B": 98, "C": 99, "D": 100, "E": 101,
    "F": 102, "G": 103, "H": 104, "I": 105, "J": 106, "K": 107, "L": 108,
    "M": 109, "N": 110, "O": 111, "P": 112, "Q": 113, "R": 114, "S": 115,
    "T": 116, "U": 117, "V": 118, "W": 119, "X": 120, "Y": 121, "Z": 122,
}


def _convert(raw: dict) -> Event | None:
    kind = raw.get("type")
    if kind == "key":
        name = str(raw.get("name", "")).upper()
        code = _key_name(name)
        key_event_type = KEYDOWN if raw.get("down") else KEYUP
        return Event(key_event_type, key=code, name=name, mod=0, unicode="",
                     scancode=0)
    if kind == "mouse":
        x, y = int(raw.get("x", 0)), int(raw.get("y", 0))
        action = raw.get("action")
        button = int(raw.get("button", 1)) or 1
        if action == "down":
            return Event(MOUSEBUTTONDOWN, pos=(x, y), button=button, touch=False)
        if action == "up":
            return Event(MOUSEBUTTONUP, pos=(x, y), button=button, touch=False)
        if action == "move":
            return Event(MOUSEMOTION, pos=(x, y), rel=(0, 0),
                         buttons=(False, False, False))
        return None
    if kind == "quit":
        return Event(QUIT)
    if kind == "resize":
        return Event(VIDEORESIZE, size=(int(raw.get("width", 0)),
                                        int(raw.get("height", 0))),
                     w=int(raw.get("width", 0)), h=int(raw.get("height", 0)))
    return None


def _fill_queue() -> None:
    if _pending:
        return
    for raw in gfxserver.SERVER.poll():
        converted = _convert(raw)
        if converted is not None:
            _pending.append(converted)


def _filtered(event_types, exclude) -> list:
    _fill_queue()
    if not event_types:
        return list(_pending)
    allowed = {event_types} if isinstance(event_types, int) else set(event_types)
    blocked = {exclude} if isinstance(exclude, int) else set(exclude or ())
    return [item for item in _pending if item.type in allowed and item.type not in blocked]


def get(eventtype=None, pump: bool = True, exclude=None):
    """Comme pygame : renvoie la **liste** des événements en attente."""
    events = _filtered(eventtype, exclude)
    if events:
        remaining = list(_pending)
        for item in events:
            remaining.remove(item)
        _pending[:] = remaining
    return events


def get_all(eventtype=None, pump: bool = True, exclude=None):
    return get(eventtype, pump, exclude)


def poll():
    _fill_queue()
    if _pending:
        return _pending.pop(0)
    return Event(0)


def wait_event():
    return wait()


def wait(timeout: float = 0):
    import time as _time

    deadline = _time.monotonic() + timeout if timeout else None
    while True:
        _fill_queue()
        if _pending:
            return _pending.pop(0)
        if deadline is not None and _time.monotonic() >= deadline:
            return Event(0)
        for raw in gfxserver.SERVER.wait(0.02):
            converted = _convert(raw)
            if converted is not None:
                _pending.append(converted)
        if _pending:
            return _pending.pop(0)


def peek(event_type, pump: bool = True):
    _fill_queue()
    for index, item in enumerate(_pending):
        if item.type == event_type:
            return _pending.pop(index)
    return Event(0)


def clear(event_type=None, pump: bool = True):
    _fill_queue()
    if event_type is None:
        _pending.clear()
    else:
        _pending[:] = [item for item in _pending if item.type != event_type]


def post(event):
    _pending.append(event)


def pump():
    _fill_queue()
    return len(_pending)


def set_grab(value):
    return None


def set_blocked(*args, **kwargs):
    return None


def get_grab():
    return False


def event_name(event_type):
    names = {value: name.lower() for name, value in globals().items()
             if name.isupper() and isinstance(value, int)}
    return names.get(event_type, "unknown")
