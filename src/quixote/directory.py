"""URL-to-object traversal.

Quixote maps a request URL onto Python objects by walking a tree of
`Directory` instances.  The publisher splits the URL path into components
(for example ``/sources/42/modify`` becomes ``['sources', '42', 'modify']``)
and hands them to the root directory's `Directory._q_traverse` method, which
consumes one component per level until it reaches a callable endpoint.

Applications build this tree by subclassing `Directory`.  Each subclass
declares which names it is willing to serve in its `Directory._q_exports`
list and provides methods (or sub-`Directory` instances) for those names.
See `Directory` for the full protocol.

This module also provides two mix-ins that customise traversal --
`AccessControlled` (run an access check before descending) and `Resolving`
(resolve exported names lazily) -- and the `export` / `subdir` decorators,
an alternative to listing names in `_q_exports` by hand.
"""

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
    """Base class for objects that map URL path components to Python objects.

    An application is a tree of `Directory` instances.  To publish content,
    subclass `Directory`, list the names you want to serve in `_q_exports`,
    and provide an attribute (method, sub-directory, or string) for each.

    Name resolution.  For a path component the traversal first calls
    `_q_translate`; if that returns a name the matching instance attribute is
    used, otherwise `_q_lookup` is called for dynamic resolution.  The
    resolved object is then either descended into (if more path components
    remain and it has its own ``_q_traverse``), called (if it is the final
    component and callable), or returned as-is.

    Protocol members a subclass typically provides:

    * ``_q_exports`` -- the whitelist of servable names (see below).
    * ``_q_index`` -- method serving the directory itself, i.e. the trailing
      ``/`` URL (the empty component ``''`` maps here).  Not defined on the
      base class; a subclass that appears at a URL endpoint must supply it.
    * ``_q_lookup(self, component)`` -- resolve names not listed statically in
      ``_q_exports`` (database ids, filenames, and so on).
    * ``_q_traverse(self, path)`` -- override to wrap traversal with
      cross-cutting behaviour (auth, logging, method checks); delegate to
      ``super()._q_traverse(path)`` for the default walk.

    Exported attributes may be plain methods (returning page content), nested
    `Directory` instances or properties returning them (traversal continues
    into them), or strings.  Only names reachable through `_q_exports` or
    `_q_lookup` are accessible; everything else is hidden from the URL space.

    Instance attributes: none.
    """

    # A list containing strings or 2-tuples of strings that map external
    # names to internal names.  A bare string exports an attribute under its
    # own name.  A ``(external, internal)`` tuple exports an attribute under a
    # different URL name, which is needed when the URL component is not a
    # valid Python identifier, e.g. ``('robots.txt', 'robots_txt')``.  The
    # empty string is implicitly mapped to the ``_q_index`` method.
    _q_exports: list[ExportItem] = []

    def _q_translate(self, component: str, /) -> str | None:
        """Map a URL path component to an exported attribute name.

        Return the instance attribute name that serves `component`, or None
        if the component is not statically exported (in which case traversal
        falls back to `_q_lookup`).  The empty component maps to
        ``'_q_index'``; a tuple entry in `_q_exports` maps its external name
        to its internal attribute name.
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
        """Dynamically resolve a path component not listed in `_q_exports`.

        Override this to serve names that are not known statically, such as
        database ids or filenames.  Return the object for `component` (usually
        a `Directory`, a callable, or a string), or None if it does not exist,
        which the traversal turns into a `TraversalError`
        (HTTP 404).  Many overrides instead raise `TraversalError` directly
        with a descriptive message.  The default implementation resolves
        nothing.
        """
        return None

    def _q_traverse(self, path: list[str], /) -> object:
        """Resolve `path` against this directory and return the result.

        `path` is the list of remaining URL components.  This consumes the
        first component (via `_q_translate` then `_q_lookup`) and then either
        recurses into the resolved object's ``_q_traverse`` when more
        components remain, calls it when it is the final component and
        callable, or returns it directly.  Raises
        `TraversalError` when a component cannot be resolved or
        a non-final component is not itself traversable.

        Override to inject behaviour that must run for every request handled
        below this directory (access control, session setup, method checks),
        delegating the actual walk to ``super()._q_traverse(path)``.
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
        """Handle a request that ends at the directory with no trailing slash.

        When a directory is the final path component but the URL omits the
        trailing ``/``, the directory itself is called.  If it has an index
        (``''`` is in `_q_exports`) and the request carries no form data, this
        redirects to the slash-terminated URL so relative links resolve
        correctly; otherwise it raises `TraversalError`.
        """
        if '' in self._q_exports and not quixote.current_request().form:
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
        """Lazily produce the object for exported `name`.

        Called the first time an exported name is traversed but is not yet an
        instance attribute; the returned object is cached as an attribute for
        subsequent requests.  Use this to defer constructing expensive
        sub-directories until they are actually requested.  Return None if the
        name cannot be resolved.
        """
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
