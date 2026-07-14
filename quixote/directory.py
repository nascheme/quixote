"""Logic for traversing directory objects and generating output."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, TypeVar, cast

import quixote
from quixote.errors import TraversalError

# Emit warning on automatic redirects when a trailing slash on the URL would
# have avoided the redirect.  The redirect requires another round-trip between
# the browser and the server.  So while writing URLs in the application code
# it's better to include the slash when needed, rather than rely on the
# automatic redirect.  For URLs entered by humans, it's common for them to
# omit the slash.  This gets turned on when DISPLAY_EXCEPTIONS true in order
# to avoid log file noise in production setups.
WARN_TRAILING_SLASH: bool = False

type ExportItem = str | tuple[str, str]
_F = TypeVar('_F', bound=Callable[..., object])
_MISSING = object()


class DirectoryClass(type):
    """A meta-class for Directory.

    Its purpose is to process methods that are exported using the export()
    and subdir() decorators.
    """

    def __new__(
        meta: type[DirectoryClass],
        classname: str,
        bases: tuple[type, ...],
        classdict: dict[str, object],
    ) -> DirectoryClass:
        cls = type.__new__(meta, classname, bases, classdict)
        exports: list[ExportItem] = []
        for key, value in classdict.items():
            if isinstance(value, property):
                # might be a property from subdir(), get the original method
                value = value.fget or value
            q_name = getattr(value, '_q_name', _MISSING)
            if q_name is not _MISSING:
                if not isinstance(q_name, str):
                    raise TypeError('_q_name must be a string')
                if q_name == key:
                    exports.append(key)
                else:
                    exports.append((q_name, key))
        if exports:
            # Only monkey with _q_exports if names are exported using the
            # decorators.
            exports += list(getattr(cls, '_q_exports', []))
            setattr(cls, '_q_exports', exports)
        return cls


class Directory(object, metaclass=DirectoryClass):
    """
    Instance attributes: none
    """

    # A list containing strings or 2-tuples of strings that map external
    # names to internal names.  Note that the empty string will be
    # implicitly mapped to '_q_index'.
    _q_exports: list[ExportItem] = []

    def _q_translate(self, component: str, /) -> str | None:
        """(component : string) -> string | None

        Translate a path component into a Python identifier.  Returning
        None signifies that the component does not exist.
        """
        if component in self._q_exports:
            if component == '':
                return '_q_index'  # implicit mapping
            else:
                return component
        else:
            # check for an explicit external to internal mapping
            for value in self._q_exports:
                if isinstance(value, tuple) and value[0] == component:
                    return value[1]
            return None

    def _q_lookup(self, component: str, /) -> object | None:
        """(component : string) -> object

        Lookup a path component and return the corresponding object (usually
        a Directory, a method or a string).  Returning None signals that the
        component does not exist.
        """
        return None

    def _q_traverse(self, path: list[str], /) -> object:
        """(path: [string]) -> object

        Traverse a path and return the result.
        """
        assert len(path) > 0
        component = path[0]
        path = path[1:]
        name = self._q_translate(component)
        if name is not None:
            obj = getattr(self, name)
        else:
            obj = self._q_lookup(component)
        if obj is None:
            raise TraversalError(
                private_msg=(
                    'directory %r has no component %r' % (self, component)
                )
            )
        if path:
            if hasattr(obj, '_q_traverse'):
                return cast(Directory, obj)._q_traverse(path)
            else:
                raise TraversalError
        elif callable(obj):
            return cast(Callable[[], object], obj)()
        else:
            return obj

    def __call__(self) -> object:
        if '' in self._q_exports and not quixote.get_request().form:
            # Fix missing trailing slash.
            path = quixote.get_path()
            if WARN_TRAILING_SLASH:
                print("Adding slash to: %r " % path)
            return quixote.redirect(path + "/")
        else:
            raise TraversalError(
                private_msg=('directory %r is not callable' % self)
            )


class AccessControlled(object):
    """
    A mix-in class that calls the _q_access() method before traversing
    into the directory.
    """

    def _q_access(self) -> None:
        pass

    def _q_traverse(self, path: list[str], /) -> object:
        self._q_access()
        return cast(
            Directory,
            super(AccessControlled, self),
        )._q_traverse(path)


class Resolving(object):
    """
    A mix-in class that provides the _q_resolve() method.  _q_resolve()
    is called if a component name appears in the _q_exports list but is
    not an instance attribute.  _q_resolve is expected to return the
    component object.
    """

    def _q_resolve(self, name: str, /) -> object | None:
        return None

    def _q_translate(self, component: str, /) -> str | None:
        name = cast(
            Directory,
            super(Resolving, self),
        )._q_translate(component)
        if name is not None and not hasattr(self, name):
            obj = self._q_resolve(name)
            setattr(self, name, obj)
        return name


def export(
    func: _F | None = None,
    name: str | None = None,
) -> _F | Callable[[_F], _F]:
    """Export a function that generates a page.

    If 'name' is not provided then the name of the page defaults to the name
    of the function (method).
    """

    def do_export(func: _F) -> _F:
        if name is not None and not isinstance(name, str):
            raise TypeError('export name must be a string')
        cast(Any, func)._q_name = func.__name__ if name is None else name
        return func

    if func is None:
        return do_export
    else:
        return do_export(func)


def subdir(
    func: _F | None = None,
    name: str | None = None,
) -> property | Callable[[_F], property]:
    """Export a function that returns a sub-directory object.

    If 'name' is not provided then the name of the directory defaults to the
    name of the function (method).
    """

    def do_export(func: _F) -> property:
        if name is not None and not isinstance(name, str):
            raise TypeError('subdir name must be a string')
        cast(Any, func)._q_name = func.__name__ if name is None else name
        return property(func)

    if func is None:
        return do_export
    else:
        return do_export(func)
