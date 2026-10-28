"""Audio : interface compatible, sans sortie son sur le canevas."""

from __future__ import annotations

_CLOCK = 0


def init(frequency: int = 44100, size: int = -16, channels: int = 2, buffer: int = 512,
         devicename=None, allowedchanges=None):
    return None


def pre_init(*args, **kwargs):
    return None


def quit():
    return None


def get_init():
    return (44100, -16, 2)


def stop():
    return None


def pause():
    return None


def unpause():
    return None


def set_num_channels(count: int):
    return None


def get_num_channels():
    return 8


def find_channel(force: bool = False):
    return None


class Sound:
    def __init__(self, file=None, buffer=None):
        self._length = 0
        self._volume = 1.0

    def play(self, loops: int = 0, maxtime: int = 0, fade_ms: int = 0):
        return None

    def stop(self):
        return None

    def fadeout(self, milliseconds: int):
        return None

    def set_volume(self, value):
        self._volume = float(value)

    def get_volume(self):
        return self._volume

    def get_length(self):
        return self._length

    def get_num_channels(self):
        return 0


class Channel:
    def __init__(self, index: int = 0):
        self.index = index

    def play(self, *args, **kwargs):
        return None

    def stop(self):
        return None

    def get_busy(self):
        return False

    def set_volume(self, value):
        return None


def get_channel(index: int = 0):
    return Channel(index)


class _Music:
    def load(self, filename):
        return None

    def unload(self):
        return None

    def play(self, loops: int = 0, start: float = 0.0, fade_ms: int = 0):
        return None

    def stop(self):
        return None

    def pause(self):
        return None

    def unpause(self):
        return None

    def fadeout(self, milliseconds: int):
        return None

    def set_volume(self, value):
        return None

    def get_volume(self):
        return 1.0

    def get_busy(self):
        return False


music = _Music()
