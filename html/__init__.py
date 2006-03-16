"""Various functions for dealing with HTML.
$HeadURL: svn+ssh://svn.mems-exchange.org/repos/trunk/quixote/html/__init__.py $
$Id: __init__.py 26631 2005-04-20 21:13:38Z dbinger $

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

import urllib

try:
    # faster C implementation
    from quixote.html._c_htmltext import htmltext, htmlescape, \
        stringify, TemplateIO
except ImportError:
    from quixote.html._py_htmltext import htmltext, htmlescape, \
        stringify, TemplateIO

ValuelessAttr = object() # magic singleton object

def htmltag(tag, xml_end=False, css_class=None, **attrs):
    """Create a HTML tag.
    """
    r = ["<%s" % tag]
    if css_class is not None:
        attrs['class'] = css_class
    for (attr, val) in attrs.items():
        if val is ValuelessAttr:
            val = attr
        if val is not None:
            r.append(' %s="%s"' % (attr,
                                   stringify(htmlescape(val))))
    if xml_end:
        r.append(" />")
    else:
        r.append(">")
    return htmltext("".join(r))


def href(url, text, title=None, **attrs):
    return (htmltag("a", href=url, title=title, **attrs) +
            htmlescape(text) +
            htmltext("</a>"))

def url_with_query(path, **attrs):
    result = htmltext(url_quote(path))
    if attrs:
        result += "?" + "&".join([url_quote(key) + "=" + url_quote(value)
                                  for key, value in attrs.items()])
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
            raise ValueError, "value is None and no fallback supplied"
        else:
            return fallback
    return urllib.quote(stringify(value))
