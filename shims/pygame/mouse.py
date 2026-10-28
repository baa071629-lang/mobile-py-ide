"""Position et boutons de la souris."""

from __future__ import annotations

from server import gfxserver


def get_pos():
    return gfxserver.SERVER.mouse


def get_pressed(num_buttons: int = 3):
    return gfxserver.SERVER.buttons


def set_visible(value):
    return 1


def get_focused():
    return True


def set_pos(position):
    gfxserver.SERVER.push_event({"type": "mouse", "action": "move",
                                 "x": int(position[0]), "y": int(position[1])})
