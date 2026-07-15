from __future__ import annotations

from typing import Any, Self

try:
    import qpy

    class qpy_TemplateIO(object):
        # The only difference between this and quixote.html.TemplateIO is the
        # .getvalue() method and the location of stringify.
        # We redefine the class from scratch only because a subclass can't
        # inherit .__iadd__ apparently: you get a TypeError that the class is
        # not the parent type.

        __slots__ = ['html', 'data']

        html: bool | int
        data: list[object]

        def __init__(self, html: bool | int = False) -> None:
            self.html = html
            self.data = []

        def __iadd__(self, other: object | None) -> Self:
            if other is not None:
                self.data.append(other)
            return self

        def __repr__(self) -> str:
            return "<%s at %x: %d chunks>" % (
                self.__class__.__name__,
                id(self),
                len(self.data),
            )

        def __str__(self) -> str:
            return qpy.stringify(self.getvalue())

        def getvalue(self) -> Any:
            klass = self.html and qpy.h8 or qpy.u8
            return klass.from_list(self.data)

except ImportError:
    pass
