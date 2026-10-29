"""Rectangle compatible pygame (sous-ensemble utile)."""

from __future__ import annotations


class Rect:
    def __init__(self, *args):
        if not args:
            x = y = w = h = 0
        elif len(args) == 1:
            value = args[0]
            if isinstance(value, Rect):
                x, y, w, h = value.x, value.y, value.width, value.height
            else:
                x, y, w, h = (list(value) + [0, 0, 0, 0])[:4]
        elif len(args) == 2:
            (x, y), (w, h) = args
        elif len(args) == 4:
            x, y, w, h = args
        else:
            x = y = w = h = 0
        self.x, self.y = int(x), int(y)
        self.width, self.height = int(w), int(h)

    # -- géométrie ------------------------------------------------------
    @property
    def left(self):
        return self.x

    @left.setter
    def left(self, value):
        self.x = int(value)

    @property
    def top(self):
        return self.y

    @top.setter
    def top(self, value):
        self.y = int(value)

    @property
    def right(self):
        return self.x + self.width

    @property
    def bottom(self):
        return self.y + self.height

    @property
    def centerx(self):
        return self.x + self.width // 2

    @property
    def centery(self):
        return self.y + self.height // 2

    @property
    def center(self):
        return (self.centerx, self.centery)

    @center.setter
    def center(self, value):
        self.x = int(value[0]) - self.width // 2
        self.y = int(value[1]) - self.height // 2

    @property
    def topleft(self):
        return (self.x, self.y)

    @topleft.setter
    def topleft(self, value):
        self.x, self.y = int(value[0]), int(value[1])

    @property
    def size(self):
        return (self.width, self.height)

    @size.setter
    def size(self, value):
        self.width, self.height = int(value[0]), int(value[1])

    @property
    def midtop(self):
        return (self.centerx, self.y)

    @midtop.setter
    def midtop(self, value):
        self.x = int(value[0]) - self.width // 2
        self.y = int(value[1])

    @property
    def midbottom(self):
        return (self.centerx, self.bottom)

    @midbottom.setter
    def midbottom(self, value):
        self.x = int(value[0]) - self.width // 2
        self.y = int(value[1]) - self.height

    @property
    def bottomleft(self):
        return (self.x, self.bottom)

    def copy(self):
        return Rect(self)

    def move(self, dx, dy):
        return Rect(self.x + dx, self.y + dy, self.width, self.height)

    def move_ip(self, dx, dy):
        self.x += int(dx)
        self.y += int(dy)

    def inflate(self, dx, dy):
        return Rect(self.x - dx // 2, self.y - dy // 2,
                    max(0, self.width + dx), max(0, self.height + dy))

    def inflate_ip(self, dx, dy):
        other = self.inflate(dx, dy)
        self.x, self.y = other.x, other.y
        self.width, self.height = other.width, other.height

    def collidepoint(self, point):
        px, py = point[0], point[1]
        return self.x <= px < self.right and self.y <= py < self.bottom

    def colliderect(self, other):
        return not (other.x >= self.right or other.right <= self.x
                    or other.y >= self.bottom or other.bottom <= self.y)

    def clamp(self, other):
        return Rect(self).clamp_ip(other)

    def clamp_ip(self, other):
        if self.width <= other.width:
            self.x = min(max(self.x, other.x), other.right - self.width)
        if self.height <= other.height:
            self.y = min(max(self.y, other.y), other.bottom - self.height)

    def contains(self, other):
        return (self.x <= other.x and self.y <= other.y
                and self.right >= other.right and self.bottom >= other.bottom)

    def union(self, other):
        left = min(self.x, other.x)
        top = min(self.y, other.y)
        return Rect(left, top, max(self.right, other.right) - left,
                    max(self.bottom, other.bottom) - top)

    def clip(self, other):
        left, top = max(self.x, other.x), max(self.y, other.y)
        right, bottom = min(self.right, other.right), min(self.bottom, other.bottom)
        if right <= left or bottom <= top:
            return Rect(self.x, self.y, 0, 0)
        return Rect(left, top, right - left, bottom - top)

    # -- protocole ------------------------------------------------------
    def __getitem__(self, index):
        return (self.x, self.y, self.width, self.height)[index]

    def __iter__(self):
        return iter((self.x, self.y, self.width, self.height))

    def __len__(self):
        return 4

    def __eq__(self, other):
        try:
            return tuple(self) == tuple(other)
        except TypeError:
            return NotImplemented

    def __bool__(self):
        return self.width > 0 and self.height > 0

    def __repr__(self):
        return f"<rect({self.x}, {self.y}, {self.width}, {self.height})>"


def rect_or_none(value):
    if value is None:
        return None
    if isinstance(value, Rect):
        return value
    if isinstance(value, int):
        return Rect(0, 0, value, value)
    return Rect(value)
