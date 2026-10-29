"""Exceptions compatibles pygame."""


class PygameError(RuntimeError):
    pass


class error(PygameError):  # noqa: N801 - nom historique de pygame
    pass
