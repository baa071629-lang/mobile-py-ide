"""Temps et cadence d'images."""

from __future__ import annotations

import time as _time

get_ticks = lambda: int(_time.monotonic() * 1000)  # noqa: E731


def init():
    return None


def quit():
    return None


def get_init():
    return True


def delay(milliseconds: int):
    _time.sleep(max(int(milliseconds), 0) / 1000)
    return int(milliseconds)


def wait(milliseconds: int):
    _time.sleep(max(int(milliseconds), 0) / 1000)
    return int(milliseconds)


def set_timer(event_type, milliseconds, loops: int = 0):
    return None


class Clock:
    def __init__(self):
        self._last = _time.monotonic()
        self._start = self._last
        self._fps_start = self._last
        self._frames = 0

    def tick(self, framerate: int = 0):
        now = _time.monotonic()
        if framerate and framerate > 0:
            target = 1.0 / float(framerate)
            remaining = target - (now - self._last)
            if remaining > 0:
                _time.sleep(remaining)
                now = _time.monotonic()
        elapsed = int((now - self._last) * 1000)
        self._last = now
        self._frames += 1
        return elapsed

    tick_busy_loop = tick

    def get_time(self):
        return int((self._last - self._start) * 1000)

    def get_rawtime(self):
        return 0

    def get_fps(self):
        elapsed = _time.monotonic() - self._fps_start
        if elapsed <= 0:
            return 0.0
        return self._frames / elapsed
