"""Various functions for dealing with HTML.

These functions are fairly simple but it is critical that they be
used correctly.  Many security problems are caused by escaping errors
(cross site scripting is one example).  The HTML and XML standards on
www.w3c.org and www.xml.com should be studied, especially the sections
on character sets, entities, attribute and values.

htmltext and htmlescape
-----------------------

This type and function are meant to be used with HTML template type.
The htmltext type designates data that does not need to be escaped and the
htmlescape() function calls str() on the argment, escapes the resulting
string and returns a htmltext instance.  htmlescape() does nothing to
htmltext instances.

url_quote
---------

Use for quoting data to be included as part of a URL, for example:

    input = "foo bar"
    ...
    '<a href="/search?keyword=%s">' % url_quote(input)

Note that URLs are usually used as attribute values and might need to have
HTML special characters escaped.  As an example of incorrect usage:

    url = 'http://example.com/?a=1&copy=0' # INCORRECT
    url = 'http://example.com/?a=1&amp;copy=0' # CORRECT
    ...
    '<a href="%s">do something</a>' % url

Old browsers would treat "&copy" as an entity reference and replace it with
the copyright character.  XML processors should treat it as an invalid entity
reference.
"""

from __future__ import annotations

import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Final, cast

_HAVE_T_STRING = sys.hexversion >= 0x030E0000

try:
    # faster C implementation
    from quixote.html._c_htmltext import (
        TemplateIO,
        htmlescape,
        htmltext,
        stringify,
    )

    if _HAVE_T_STRING:
        from quixote.html._c_htmltext import htmlformat
except ImportError:
    from quixote.html._py_htmltext import (  # noqa: F401
        TemplateIO,
        htmlescape,
        htmltext,
        stringify,
    )

    if _HAVE_T_STRING:
        from quixote.html._py_htmltext import htmlformat  # noqa: F401

from quixote.html._py_htmltext import _wraparg  # noqa: E402

ValuelessAttr: Final = object()  # magic singleton object


def htmltag(
    tag: str,
    xml_end: bool | int = False,
    css_class: str | None = None,
    **attrs: object,
) -> htmltext:
    """Build an HTML start tag with escaped attribute values.

    Each keyword argument becomes an attribute; its value is escaped with
    `htmlescape`, so plain-str values cannot break double-quoted attribute
    syntax.  This does not validate URL schemes, JavaScript, CSS, or other
    attribute-specific meanings.  An attribute whose value is None is omitted.
    An attribute whose value is `ValuelessAttr` is emitted as
    ``name="name"``.  Pass ``css_class`` for the ``class`` attribute (a
    reserved word in Python), or use ``**{'class': ...}``.  Set
    ``xml_end=True`` to emit a self-closing tag (``<br />``) instead of an
    open tag.  Returns `htmltext`.

    >>> from quixote.html import htmltag
    >>> print(htmltag('br', xml_end=True))
    <br />
    >>> print(htmltag('div', css_class='box', id='x'))
    <div id="x" class="box">
    >>> print(htmltag('input', type='text', value='a&b'))
    <input type="text" value="a&amp;b">
    """
    r = ["<%s" % tag]
    if css_class is not None:
        attrs['class'] = css_class
    for attr, val in attrs.items():
        if val is ValuelessAttr:
            val = attr
        if val is not None:
            r.append(' %s="%s"' % (attr, stringify(htmlescape(val))))
    if xml_end:
        r.append(" />")
    else:
        r.append(">")
    return htmltext("".join(r))


def href(
    url: object,
    text: object,
    title: object | None = None,
    **attrs: object,
) -> htmltext:
    """Build a complete ``<a>`` anchor element.

    `url` becomes the ``href`` and is HTML-escaped, but is not URL-quoted or
    scheme-validated; callers must pass an already valid/quoted URL.  `text`
    becomes the link body and is HTML-escaped, as are `title` and any extra
    attributes.  Returns `htmltext`.

    >>> from quixote.html import href
    >>> print(href('/a?x=1&y=2', 'go'))
    <a href="/a?x=1&amp;y=2">go</a>
    """
    return (
        htmltag(
            "a",
            **cast(Any, {"href": url, "title": title, **attrs}),
        )
        + htmlescape(text)
        + htmltext("</a>")
    )


def url_with_query(path: object, **attrs: object) -> htmltext:
    """Build a URL from `path` and a query string of the keyword arguments.

    `path` is URL-quoted first, so pass a bare path; existing ``?``, ``#``,
    ``=``, and ``&`` characters in it are percent-encoded rather than treated
    as URL delimiters.  Keys and values are URL-quoted, then the ``key=value``
    pairs (sorted by key) are joined with ``&`` and appended.  The result is
    `htmltext`, so the ``&`` separators are safe to embed in an attribute.

    >>> from quixote.html import url_with_query
    >>> print(url_with_query('/search', q='a b', p='1'))
    /search?p=1&amp;q=a%20b
    """
    result = htmltext(url_quote(path))
    if attrs:
        attrs = dict(sorted(attrs.items()))
        result += "?" + "&".join(
            [
                url_quote(key) + "=" + url_quote(value)
                for key, value in attrs.items()
            ]
        )
    return result


def nl2br(value: object) -> htmltext:
    """Escape `value` and insert ``<br />`` tags before LF characters.

    Returns `htmltext` with the original LF characters preserved after each
    break.  Lone CR characters are unchanged.
    """
    text = htmlescape(value)
    return htmltext(text.s.replace('\n', '<br />\n'))


def url_quote(value: object | None, fallback: str | None = None) -> str:
    """Quote `value` for safe inclusion in a URL (see ``urllib.parse.quote``).

    Returns a plain `str`.  If `value` is None, `fallback` is returned
    unquoted when supplied, otherwise a ValueError is raised.  Note the result
    is URL-quoted, not HTML-escaped: when placing a URL in an attribute value,
    HTML-escape it with `htmlescape` or an escaping `htmltext` formatting
    operation so ``&`` in a query string is not read as an entity.
    """
    if value is None:
        if fallback is None:
            raise ValueError("value is None and no fallback supplied")
        else:
            return fallback
    return urllib.parse.quote(stringify(value))


def _q_join(*args: object) -> htmltext:
    # Used by f-strings to join the {..} parts
    return htmltext('').join(args)


def _q_format(
    value: object,
    conversion: int = -1,
    format_spec: object | None = None,
) -> htmltext:
    # Used by f-strings to format the {..} parts
    if conversion == -1 and format_spec is None:
        return htmlescape(value)  # simple and fast case
    if conversion == -1:
        fmt = '{%s}'
    else:
        conversion_char = chr(conversion)
        if conversion_char == 'r':
            fmt = '{%s!r}'
        elif conversion_char == 's':
            fmt = '{%s!s}'
        elif conversion_char == 'a':
            fmt = '{%s!a}'
        else:
            raise RuntimeError('invalid conversion %r' % conversion_char)
    arg = _wraparg(value)
    if format_spec:
        fmt = fmt % (':' + str(format_spec))
    else:
        fmt = fmt % ''
    return htmltext(fmt.format(arg))


_saved: tuple[Any, Any, Any, Any] | None = None


def use_qpy() -> None:
    """
    Switch to using 'qpy' as an alternative.
    """
    import qpy

    from .qpy_templateio import qpy_TemplateIO

    global _saved, htmltext, stringify, htmlescape, TemplateIO
    if _saved is None:
        _saved = (htmltext, stringify, htmlescape, TemplateIO)

        htmltext = qpy.h8
        stringify = qpy.stringify
        htmlescape = qpy.h8.quote
        TemplateIO = qpy_TemplateIO


def cleanup_qpy() -> None:
    global _saved, htmltext, stringify, htmlescape, TemplateIO

    if _saved is None:
        raise RuntimeError('qpy support is not active')
    htmltext, stringify, htmlescape, TemplateIO = _saved
    _saved = None


_ETAGO_PAT = re.compile(r'</')


def js_escape(s: object) -> htmltext:
    r"""Escape ETAGO sequences in JavaScript embedded in HTML.

    When embedding JavaScript code inside a <script> tag, the ETAGO
    (i.e. the two character sequence "</") must be escaped to avoid
    premature ending of the script element.  This function only replaces
    literal "</" with "<\/"; it is not a general JavaScript string or code
    escaper and must not be used to interpolate arbitrary data.

    >>> from quixote.html import js_escape
    >>> print(js_escape('</script>'))
    <\/script>
    """
    # assume the sequence occurs inside a string, use backslash escape
    s = stringify(s)
    return htmltext(_ETAGO_PAT.sub(r'<\/', s))


def htmltemplate() -> TemplateIO:
    """Return a new `TemplateIO` in HTML mode."""
    return TemplateIO(html=True)
