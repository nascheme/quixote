"""Various functions for dealing with HTML.

These functions are fairly simple but it is critical that they be
used correctly.  Many security problems are caused by escaping errors
(cross site scripting is one example).  The HTML and XML standards on
www.w3c.org and www.xml.com should be studied, especially the sections
on character sets, entities, attribute and values.

htmltext and htmlescape
-----------------------

This type and function are meant to be used with [html] PTL template type.
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

import re
import urllib.request, urllib.parse, urllib.error

try:
    # faster C implementation
    from quixote.html._c_htmltext import (
        htmltext,
        htmlescape,
        stringify,
        TemplateIO,
    )
except ImportError:
    from quixote.html._py_htmltext import (  # noqa: F401
        htmltext,
        htmlescape,
        stringify,
        TemplateIO,
    )

from quixote.html._py_htmltext import _wraparg

ValuelessAttr = object()  # magic singleton object


def htmltag(tag, xml_end=False, css_class=None, **attrs):
    """Create a HTML tag."""
    r = ["<%s" % tag]
    if css_class is not None:
        attrs['class'] = css_class
    for (attr, val) in attrs.items():
        if val is ValuelessAttr:
            val = attr
        if val is not None:
            r.append(' %s="%s"' % (attr, stringify(htmlescape(val))))
    if xml_end:
        r.append(" />")
    else:
        r.append(">")
    return htmltext("".join(r))


def href(url, text, title=None, **attrs):
    return (
        htmltag("a", href=url, title=title, **attrs)
        + htmlescape(text)
        + htmltext("</a>")
    )


def url_with_query(path, **attrs):
    result = htmltext(url_quote(path))
    if attrs:
        attrs = sorted(attrs.items())
        result += "?" + "&".join(
            [url_quote(key) + "=" + url_quote(value) for key, value in attrs]
        )
    return result


def nl2br(value):
    """nl2br(value : any) -> htmltext

    Insert <br /> tags before newline characters.
    """
    text = htmlescape(value)
    return htmltext(text.s.replace('\n', '<br />\n'))


def url_quote(value, fallback=None):
    """url_quote(value : any [, fallback : string]) -> string

    Quotes 'value' for use in a URL; see urllib.quote().  If value is None,
    then the behavior depends on the fallback argument.  If it is not
    supplied then an error is raised.  Otherwise, the fallback value is
    returned unquoted.
    """
    if value is None:
        if fallback is None:
            raise ValueError("value is None and no fallback supplied")
        else:
            return fallback
    return urllib.parse.quote(stringify(value))


def _q_join(*args):
    # Used by f-strings to join the {..} parts
    return htmltext('').join(args)


def _q_format(value, conversion=-1, format_spec=None):
    # Used by f-strings to format the {..} parts
    if conversion == -1 and format_spec is None:
        return htmlescape(value)  # simple and fast case
    if conversion == -1:
        fmt = '{%s}'
    else:
        conversion = chr(conversion)
        if conversion == 'r':
            fmt = '{%s!r}'
        elif conversion == 's':
            fmt = '{%s!s}'
        elif conversion == 'a':
            fmt = '{%s!a}'
        else:
            assert 0, 'invalid conversion %r' % conversion
    arg = _wraparg(value)
    if format_spec:
        fmt = fmt % (':' + str(format_spec))
    else:
        fmt = fmt % ''
    return htmltext(fmt.format(arg))


_saved = None


def use_qpy():
    """
    Switch to using 'qpy' as an alternative.
    """
    import qpy
    from .qpy_templateio import qpy_TemplateIO

    global _saved, htmltext, stringify, htmlescape, TemplateIO
    if not _saved:
        _saved = (htmltext, stringify, htmlescape, TemplateIO)

        htmltext = qpy.h8
        stringify = qpy.stringify
        htmlescape = qpy.h8.quote
        TemplateIO = qpy_TemplateIO


def cleanup_qpy():
    global _saved, htmltext, stringify, htmlescape, TemplateIO

    (htmltext, stringify, htmlescape, TemplateIO) = _saved
    _saved = None


_ETAGO_PAT = re.compile(r'</')


def js_escape(s):
    """Escape Javascript code to be embedded in HTML.

    When embedding Javascript code inside a <script> tag, the ETAGO
    (i.e. the two character sequence "</") must be escaped to avoid
    premature ending of the script element.
    """
    # assume the sequence occurs inside a string, use backslash escape
    s = stringify(s)
    return htmltext(_ETAGO_PAT.sub(r'<\/', s))
