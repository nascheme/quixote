"""Python implementation of the htmltext type, the htmlescape function and
TemplateIO.
"""

from __future__ import annotations

from collections.abc import Iterable
from types import NotImplementedType
from typing import TYPE_CHECKING, Any, Never, Self

try:
    from string.templatelib import Interpolation, Template

    _HAVE_T_STRING = True
except ImportError:
    _HAVE_T_STRING = False


def _escape_string(s: object) -> str:
    if isinstance(s, bytes):
        raise TypeError('escape_string no longer accepts bytes')
    if not isinstance(s, str):
        raise TypeError('string object required')
    s = s.replace("&", "&amp;")
    s = s.replace("<", "&lt;")
    s = s.replace(">", "&gt;")
    s = s.replace('"', "&quot;")
    return s


# backwards comptibility, unneeded in Python 3
if TYPE_CHECKING:

    def stringify(value: object = '') -> str:
        """Coerce `value` to a plain `str` (an alias for the builtin ``str``).

        For an `htmltext` argument this returns its underlying markup string.
        Provided for backwards compatibility and readability; new code can use
        ``str`` directly.
        """
        return str(value)
else:
    stringify = str


class htmltext(object):
    """A string-like type marking text that is already safe HTML markup.

    Wrapping a value in `htmltext` asserts that it is trusted markup and must
    not be escaped again.  Templating (PTL, `TemplateIO`, and the `%`, `+`,
    `format`, and `join` operations below) escapes plain `str` operands but
    passes `htmltext` through untouched, so mixing the two produces correct,
    minimally-escaped output.  Only wrap markup you know is safe; never wrap
    unescaped user input.  Use `htmlescape` to turn untrusted text into
    `htmltext`.

    The HTML-special characters escaped in plain-str operands are ``&``,
    ``<``, ``>``, and ``"``.

    >>> from quixote.html import htmltext
    >>> htmltext('<b>safe</b>')          # already-safe markup, left as-is
    <htmltext '<b>safe</b>'>
    >>> print(htmltext('<b>') + '<i>')   # a plain str operand is escaped
    <b>&lt;i&gt;
    >>> print(htmltext('%s') % '<i>')    # %-formatting escapes the argument
    &lt;i&gt;
    """

    __slots__ = ['s']

    s: str

    def __init__(self, s: object) -> None:
        self.s = str(s)

    # XXX make read-only
    # def __setattr__(self, name, value):
    #    raise AttributeError, 'immutable object'

    def __getstate__(self) -> Never:
        raise ValueError('htmltext objects should not be pickled')

    def __repr__(self) -> str:
        return '<htmltext %r>' % self.s

    def __str__(self) -> str:
        return self.s

    def __len__(self) -> int:
        return len(self.s)

    def __eq__(self, other: object) -> bool:
        if isinstance(other, htmltext):
            return self.s == other.s
        return self.s == other

    def __lt__(self, other: str | htmltext) -> bool:
        if isinstance(other, htmltext):
            return self.s < other.s
        return self.s < other

    def __hash__(self) -> int:
        return hash(self.s)

    def __mod__(self, args: object) -> htmltext:
        if isinstance(args, tuple):
            return htmltext(self.s % tuple(map(_wraparg, args)))
        else:
            return htmltext(self.s % _wraparg(args))

    def format(self, *args: object, **kwargs: object) -> htmltext:
        """Like ``str.format`` but escape any plain-str arguments.

        The template itself (``self``) is trusted markup; each substituted
        value is escaped unless it is already `htmltext`.
        """
        wrapped_args = list(map(_wraparg, args))
        wrapped_kwargs = {
            key: _wraparg(value) for key, value in kwargs.items()
        }
        return htmltext(self.s.format(*wrapped_args, **wrapped_kwargs))

    def __add__(self, other: str | htmltext) -> htmltext | NotImplementedType:
        if isinstance(other, str):
            return htmltext(self.s + _escape_string(other))
        elif isinstance(other, htmltext):
            return htmltext(self.s + other.s)
        else:
            return NotImplemented

    def __radd__(self, other: str) -> htmltext | NotImplementedType:
        if isinstance(other, str):
            return htmltext(_escape_string(other) + self.s)
        else:
            return NotImplemented

    def __mul__(self, n: int) -> htmltext:
        return htmltext(self.s * n)

    def join(self, items: Iterable[object]) -> htmltext:
        """Join `items` with this separator, escaping plain-str items.

        Like ``str.join``, but `htmltext` items pass through unescaped while
        plain `str` items are escaped.  The common idiom
        ``htmltext('').join(parts)`` concatenates a list of rendered fragments
        safely.  Items must be `str` or `htmltext`.
        """
        quoted_items: list[str] = []
        for item in items:
            if isinstance(item, htmltext):
                quoted_items.append(str(item))
            elif isinstance(item, str):
                quoted_items.append(_escape_string(item))
            else:
                raise TypeError(
                    'join() requires string arguments (got %r)' % item
                )
        return htmltext(self.s.join(quoted_items))

    def startswith(self, s: str | htmltext) -> bool:
        if isinstance(s, htmltext):
            s = s.s
        else:
            s = _escape_string(s)
        return self.s.startswith(s)

    def endswith(self, s: str | htmltext) -> bool:
        if isinstance(s, htmltext):
            s = s.s
        else:
            s = _escape_string(s)
        return self.s.endswith(s)

    def replace(
        self,
        old: str | htmltext,
        new: str | htmltext,
        count: int = -1,
    ) -> htmltext:
        if isinstance(old, htmltext):
            old = old.s
        else:
            old = _escape_string(old)
        if isinstance(new, htmltext):
            new = new.s
        else:
            new = _escape_string(new)
        return htmltext(self.s.replace(old, new, count))

    def lower(self) -> htmltext:
        return htmltext(self.s.lower())

    def upper(self) -> htmltext:
        return htmltext(self.s.upper())

    def capitalize(self) -> htmltext:
        return htmltext(self.s.capitalize())


class _QuoteWrapper(object):
    # helper for htmltext class __mod__

    __slots__ = ['value']

    value: Any

    def __init__(self, value: Any) -> None:
        self.value = value

    def __str__(self) -> str:
        return _escape_string(str(self.value))

    def __repr__(self) -> str:
        return _escape_string(repr(self.value))

    def __getitem__(self, key: object) -> str | int | float | _QuoteWrapper:
        return _wraparg(self.value[key])


def _wraparg(arg: object) -> str | int | float | _QuoteWrapper:
    if isinstance(arg, htmltext):
        return str(arg)
    elif isinstance(arg, str):
        return _escape_string(arg)
    elif isinstance(arg, int) or isinstance(arg, float):
        # ints, floats are okay
        return arg
    else:
        # everything is gets wrapped
        return _QuoteWrapper(arg)


def htmlescape(s: object) -> htmltext:
    """Escape untrusted text and return it as `htmltext`.

    Coerce `s` to a string and escape the HTML markup characters ``&``,
    ``<``, ``>``, and ``"``.  An argument that is already `htmltext` is
    returned unchanged, so calling `htmlescape` twice does not double-escape.
    This is the safe way to turn user-supplied data into `htmltext`.

    >>> from quixote.html import htmlescape
    >>> print(htmlescape('a < b & c'))
    a &lt; b &amp; c
    """
    if isinstance(s, htmltext):
        return s
    else:
        s = str(s)
    # inline _escape_string for speed
    s = s.replace("&", "&amp;")  # must be done first
    s = s.replace("<", "&lt;")
    s = s.replace(">", "&gt;")
    s = s.replace('"', "&quot;")
    return htmltext(s)


class TemplateIO(object):
    """Accumulate output fragments and join them into a single result.

    A `TemplateIO` collects values appended with ``+=`` (or by calling it) and
    concatenates them on `getvalue`.  It backs the ``@ptl_html`` templating
    mechanism but can also be used directly to build output imperatively.
    Pass ``html=True`` for HTML mode, in which each fragment is run through
    `htmlescape` on `getvalue` so plain-str fragments are escaped and
    `htmltext` fragments are preserved; the default plain mode simply
    stringifies each fragment.
    """

    __slots__ = ['html', 'data']

    html: bool | int
    data: list[object]

    def __init__(self, html: bool | int = False) -> None:
        self.html = html
        self.data = []

    def __call__(self, s: object | None) -> None:
        if s is not None:
            self.data.append(s)

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
        return str(self.getvalue())

    def getvalue(self) -> htmltext | str:
        """Return the accumulated output.

        In HTML mode this is an `htmltext` of the escaped-and-joined
        fragments; otherwise a plain `str` of the stringified fragments.
        """
        if self.html:
            return htmltext('').join(map(htmlescape, self.data))
        else:
            return ''.join(map(str, self.data))


if _HAVE_T_STRING:

    def htmlformat(template: Template) -> htmltext:
        """Format htmltext using a t-string as input."""
        if not isinstance(template, Template):
            raise TypeError(f'require t-string, got {template!r}')
        if (
            not template.values
            and not template.interpolations
            and len(template.strings) == 1
        ):
            return htmltext(template.strings[0])
        parts: list[Any] = []
        for item in template:
            match item:
                case str() as s:
                    parts.append(s)
                case Interpolation(value, _, conversion, format_spec):
                    if conversion is not None:
                        raise ValueError(
                            'conversion not supported for htmlformat'
                        )
                    value = format(_wraparg(value), format_spec)
                    parts.append(value)
        return htmltext("".join(parts))
