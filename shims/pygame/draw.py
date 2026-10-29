"""Primitives de dessin pygame."""

from __future__ import annotations

from .color import css, parse
from .rect import Rect, rect_or_none


def _target(surface):
    return surface


def rect(surface, color, rect, width: int = 0, border_radius: int = 0,
         border_top_left_radius: int = -1, **kwargs):
    area = rect if isinstance(rect, Rect) else Rect(rect)
    surface._emit("rect", x=area.x, y=area.y, w=area.width, h=area.height,
                  color=css(color), fill=width <= 0, width=max(int(width), 1))
    return area


def polygon(surface, color, points, width: int = 0):
    pts = [[int(p[0]), int(p[1])] for p in points]
    surface._emit("polygon", points=pts, color=css(color), fill=width <= 0,
                  width=max(int(width), 1))
    if pts:
        xs = [p[0] for p in pts]
        ys = [p[1] for p in pts]
        return Rect(min(xs), min(ys), max(xs) - min(xs), max(ys) - min(ys))
    return Rect(0, 0, 0, 0)


def circle(surface, color, center, radius, width: int = 0, **kwargs):
    x, y = int(center[0]), int(center[1])
    r = int(radius)
    surface._emit("circle", x=x, y=y, r=r, color=css(color), fill=width <= 0,
                  width=max(int(width), 1))
    return Rect(x - r, y - r, r * 2, r * 2)


def ellipse(surface, color, rect, width: int = 0, **kwargs):
    area = Rect(rect)
    surface._emit("ellipse", x=area.x, y=area.y, w=area.width, h=area.height,
                  color=css(color), fill=width <= 0, width=max(int(width), 1))
    return area


def line(surface, color, start_pos, end_pos, width: int = 1):
    surface._emit("line", x1=int(start_pos[0]), y1=int(start_pos[1]),
                  x2=int(end_pos[0]), y2=int(end_pos[1]),
                  color=css(color), width=max(int(width), 1))
    return Rect(min(start_pos[0], end_pos[0]), min(start_pos[1], end_pos[1]),
                abs(end_pos[0] - start_pos[0]), abs(end_pos[1] - start_pos[1]))


def aaline(surface, color, start_pos, end_pos, blend: int = 1):
    return line(surface, color, start_pos, end_pos, 1)


def lines(surface, color, closed, points, width: int = 1):
    pts = [[int(p[0]), int(p[1])] for p in points]
    surface._emit("lines", points=pts, color=css(color), closed=bool(closed),
                  width=max(int(width), 1))
    if not pts:
        return Rect(0, 0, 0, 0)
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    return Rect(min(xs), min(ys), max(xs) - min(xs), max(ys) - min(ys))


def aalines(surface, color, closed, points, blend: int = 1):
    return lines(surface, color, closed, points, 1)


def arc(surface, color, rect, start_angle, stop_angle, width: int = 1):
    area = Rect(rect)
    surface._emit("arc", x=area.x, y=area.y, w=area.width, h=area.height,
                  start=float(start_angle), stop=float(stop_angle),
                  color=css(color), width=max(int(width), 1))
    return area


def pie_ignore(surface, color, rect, start, stop, width=0):  # pragma: no cover
    return ellipse(surface, color, rect, width)
