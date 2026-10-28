"""Sprites et groupes (sous-ensemble compatible)."""

from __future__ import annotations

from .rect import Rect


class Sprite:
    def __init__(self, *groups):
        self.image = None
        self.rect = None
        self._groups = list(groups)
        for group in groups:
            group.add_internal(self)

    def add(self, *groups):
        for group in groups:
            group.add_internal(self)

    def remove(self, *groups):
        for group in groups:
            group.remove_internal(self)

    def kill(self):
        for group in list(self._groups):
            group.remove_internal(self)

    def alive(self):
        return bool(self._groups)

    def groups(self):
        return list(self._groups)

    def update(self, *args, **kwargs):
        return None


class Group:
    def __init__(self, *sprites):
        self._sprites: list[Sprite] = []
        for sprite in sprites:
            self.add(sprite)

    def add(self, *sprites):
        for sprite in sprites:
            self.add_internal(sprite)

    def add_internal(self, sprite):
        if sprite not in self._sprites:
            self._sprites.append(sprite)
            if self not in sprite._groups:
                sprite._groups.append(self)

    def remove(self, *sprites):
        for sprite in sprites:
            self.remove_internal(sprite)

    def remove_internal(self, sprite):
        if sprite in self._sprites:
            self._sprites.remove(sprite)
        if self in sprite._groups:
            sprite._groups.remove(self)

    def has(self, *sprites):
        return all(sprite in self._sprites for sprite in sprites)

    def sprites(self):
        return list(self._sprites)

    def copy(self):
        clone = Group()
        clone._sprites = list(self._sprites)
        return clone

    def empty(self):
        self._sprites.clear()

    def update(self, *args, **kwargs):
        for sprite in list(self._sprites):
            sprite.update(*args, **kwargs)

    def draw(self, surface, *args, **kwargs):
        rects = []
        for sprite in list(self._sprites):
            if getattr(sprite, "image", None) is not None and sprite.rect is not None:
                surface.blit(sprite.image, sprite.rect.topleft)
                rects.append(sprite.rect)
        return rects

    def clear(self, surface, background):
        for sprite in list(self._sprites):
            if sprite.rect is not None:
                surface.fill(background, sprite.rect)

    def __iter__(self):
        return iter(list(self._sprites))

    def __len__(self):
        return len(self._sprites)

    def __contains__(self, sprite):
        return sprite in self._sprites


class RenderPlain(Group):
    pass


class RenderClear(Group):
    def __init__(self, *sprites):
        super().__init__(*sprites)
        self.background = None


class LayeredUpdates(Group):
    def __init__(self, *sprites, **kwargs):
        super().__init__(*sprites)


def spritecollide(sprite, group, dokill: bool, collided=None):
    result = []
    for other in list(group):
        if other is sprite or other.rect is None or sprite.rect is None:
            continue
        if sprite.rect.colliderect(other.rect):
            result.append(other)
            if dokill:
                other.kill()
    return result


def groupcollide(groupa, groupb, dokilla: bool, dokillb: bool, collided=None):
    hits = {}
    for first in list(groupa):
        found = spritecollide(first, groupb, dokillb, collided)
        if found:
            hits[first] = found
    if dokilla:
        for first in list(hits):
            first.kill()
    return hits


def collide_rect(a, b):
    return a.rect.colliderect(b.rect)


def collide_circle(a, b):
    ax, ay = a.rect.center
    bx, by = b.rect.center
    return (ax - bx) ** 2 + (ay - by) ** 2 <= (a.rect.width / 2 + b.rect.width / 2) ** 2


rect = collide_rect
circle = collide_circle
