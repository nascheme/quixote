from quixote.html import _py_htmltext
from quixote.html import href, url_with_query, url_quote, nl2br
from quixote.test.utest import UTest

markupchars = '<>&"'
quotedchars = '&lt;&gt;&amp;&quot;'
unicodechars = '\u1234'
high_code = '\U000e0030'

# Byte types...
markupbytes = b'<>&"'
quotedbytes = b'&lt;&gt;&amp;&quot;'
bytebytes = b'\x01'


class Wrapper:
    def __init__(self, s):
        self.s = s

    def __repr__(self):
        return self.s

    def __str__(self):
        return self.s


class BrokenError(Exception):
    pass


class Broken:
    def __str__(self):
        raise BrokenError('eieee')

    def __repr__(self):
        raise BrokenError('eieee')


htmltext = escape = htmlescape = TemplateIO = None


class HTMLTest(UTest):
    def check_href(self):
        assert str(href('/foo/bar', 'bar')) == '<a href="/foo/bar">bar</a>'

    def check_url_with_query(self):
        assert str(url_with_query('/f/b', a='1')) == '/f/b?a=1'
        assert (
            str(url_with_query('/f/b', a='1', b='3 4'))
            == '/f/b?a=1&amp;b=3%204'
        )

    def check_nl2br(self):
        assert str(nl2br('a\nb\nc')) == 'a<br />\nb<br />\nc'

    def check_url_quote(self):
        assert url_quote('abc') == 'abc'
        assert url_quote('a b c') == 'a%20b%20c'
        assert url_quote(None, fallback='abc') == 'abc'


class HTMLTextTest(UTest):
    def check_init(self):
        assert str(htmltext('foo')) == 'foo'
        assert str(htmltext(markupchars)) == markupchars
        assert str(htmltext(unicodechars)) == unicodechars
        assert str(htmltext(str(markupchars))) == markupchars
        assert str(htmltext(None)) == 'None'
        assert str(htmltext(1)) == '1'
        try:
            htmltext(Broken())
            assert 0
        except BrokenError:
            pass

    def check_escape(self):
        assert htmlescape(markupchars) == quotedchars
        assert isinstance(htmlescape(markupchars), htmltext)
        assert escape(markupchars) == quotedchars
        assert escape(unicodechars) == unicodechars
        assert escape(high_code) == high_code
        assert type(escape(markupchars)) == type(markupchars)
        assert isinstance(escape(markupchars), str)
        assert htmlescape(htmlescape(markupchars)) == quotedchars

        # Now try to pass bytes...
        try:
            escape(markupbytes)
            assert 0
        except TypeError:
            pass

        # ...and now not a string at all
        try:
            escape(1)
            assert 0
        except TypeError:
            pass

    def check_cmp(self):
        s = htmltext("foo")
        assert s == 'foo'
        assert s != 'bar'
        assert s == htmltext('foo')
        assert s != htmltext('bar')
        assert htmltext('\\u1234') == '\\u1234'
        assert htmltext('1') != 1
        assert 1 != s

    def check_len(self):
        assert len(htmltext('foo')) == 3
        assert len(htmltext(markupchars)) == len(markupchars)
        assert len(htmlescape(markupchars)) == len(quotedchars)

    def check_hash(self):
        assert hash(htmltext('foo')) == hash('foo')
        assert hash(htmltext(markupchars)) == hash(markupchars)
        assert hash(htmlescape(markupchars)) == hash(quotedchars)

    def check_concat(self):
        s = htmltext("foo")
        assert s + 'bar' == "foobar"
        assert 'bar' + s == "barfoo"
        assert s + htmltext('bar') == "foobar"
        assert s + markupchars == "foo" + quotedchars
        assert isinstance(s + markupchars, htmltext)
        assert markupchars + s == quotedchars + "foo"
        assert isinstance(markupchars + s, htmltext)
        assert markupchars + htmltext('') == quotedchars
        try:
            s + 1
            assert 0
        except TypeError:
            pass
        try:
            1 + s
            assert 0
        except TypeError:
            pass

        assert repr(htmltext('a') + htmltext('b')) == "<htmltext 'ab'>"

    def check_repeat(self):
        s = htmltext('a')
        assert s * 3 == "aaa"
        assert isinstance(s * 3, htmltext)
        assert htmlescape(markupchars) * 3 == quotedchars * 3
        try:
            s * 'a'
            assert 0
        except TypeError:
            pass
        try:
            'a' * s
            assert 0
        except TypeError:
            pass
        try:
            s * s
            assert 0
        except TypeError:
            pass

    def check_format(self):
        u_fmt = htmltext('%s')
        assert u_fmt % 'fooble' == "fooble"
        assert isinstance(u_fmt % 'wibblefoo', htmltext)
        assert u_fmt % markupchars == quotedchars

        assert u_fmt % None == "None"
        assert u_fmt % unicodechars == unicodechars
        assert u_fmt % htmltext(unicodechars) == unicodechars
        assert htmltext('%r') % Wrapper(markupchars) == quotedchars
        assert htmltext('%r') % unicodechars == repr(unicodechars)
        assert htmltext('%s%s') % ('foo', htmltext(markupchars)) == (
            "foo" + markupchars
        )
        assert htmltext('%d') % 10 == "10"
        assert htmltext('%.1f') % 10 == "10.0"

        try:
            htmltext('%r') % Broken()
            assert 0
        except BrokenError:
            pass

        assert htmltext('%d') % 12300000000000000000 == "12300000000000000000"

    def check_dict_format(self):
        args = {'a': 'foo&', 'b': htmltext('bar&')}
        result = "foo&amp; 'foo&amp;' bar&"
        assert htmltext('%(a)s %(a)r %(b)s') % args == result
        assert htmltext('%(a)s') % {'a': 'foo&'} == "foo&amp;"
        assert isinstance(htmltext('%(a)s') % {'a': 'a'}, htmltext)
        assert htmltext('%s') % {'a': 'foo&'} == "{'a': 'foo&amp;'}"
        try:
            htmltext('%(a)s') % 1
            assert 0
        except TypeError:
            pass
        try:
            htmltext('%(a)s') % {}
            assert 0
        except KeyError:
            pass
        assert htmltext('') % {} == ''
        assert htmltext('%%') % {} == '%'

    def check_format_method(self):
        assert htmltext('{}').format('foo') == 'foo'
        assert htmltext('{}').format('foo', **{}) == 'foo'
        try:
            htmltext('{}').format()
            assert 0
        except IndexError:
            pass
        assert htmltext('{a}').format(a='foo') == 'foo'
        args = {'a': 'foo&', 'b': htmltext('bar&')}
        result = "foo&amp; bar&"
        assert htmltext('{a} {b}').format(**args) == result

    def check_join(self):
        assert htmltext(' ').join(['foo', 'bar']) == "foo bar"
        assert (
            htmltext(' ').join(['foo', markupchars]) == "foo " + quotedchars
        )
        assert (
            htmlescape(markupchars).join(['foo', 'bar'])
            == "foo" + quotedchars + "bar"
        )
        assert (
            htmltext(' ').join([htmltext(markupchars), 'bar'])
            == markupchars + " bar"
        )
        assert isinstance(htmltext('').join([]), htmltext)
        assert htmltext(' ').join([unicodechars]) == unicodechars
        assert htmltext(' ').join(['']) == ''
        try:
            htmltext('').join(1)
            assert 0
        except TypeError:
            pass
        try:
            htmltext('').join([1])
            assert 0
        except TypeError:
            pass

    def check_startswith(self):
        assert htmltext('foo').startswith('fo')
        assert htmlescape(markupchars).startswith(markupchars[:3])
        assert htmltext(markupchars).startswith(htmltext(markupchars[:3]))
        try:
            htmltext('').startswith(1)
            assert 0
        except TypeError:
            pass

    def check_endswith(self):
        assert htmltext('foo').endswith('oo')
        assert htmlescape(markupchars).endswith(markupchars[-3:])
        assert htmltext(markupchars).endswith(htmltext(markupchars[-3:]))
        try:
            htmltext('').endswith(1)
            assert 0
        except TypeError:
            pass

    def check_replace(self):
        assert htmlescape('&').replace('&', 'foo') == "foo"
        assert htmltext('&').replace(htmltext('&'), 'foo') == "foo"
        assert htmltext('foo').replace('foo', htmltext('&')) == "&"
        assert isinstance(htmltext('a').replace('a', 'b'), htmltext)
        try:
            htmltext('').replace(1, 'a')
            assert 0
        except TypeError:
            pass

    def check_lower(self):
        assert htmltext('aB').lower() == "ab"
        assert isinstance(htmltext('a').lower(), htmltext)

    def check_upper(self):
        assert htmltext('aB').upper() == "AB"
        assert isinstance(htmltext('a').upper(), htmltext)

    def check_capitalize(self):
        assert htmltext('aB').capitalize() == "Ab"
        assert isinstance(htmltext('a').capitalize(), htmltext)


class TemplateTest(UTest):
    def check_init(self):
        TemplateIO()
        TemplateIO(html=True)
        TemplateIO(html=False)

    def check_text_iadd(self):
        t = TemplateIO()
        assert t.getvalue() == ''
        t += "abcd"
        assert t.getvalue() == 'abcd'
        t += None
        assert t.getvalue() == 'abcd'
        t += 123
        assert t.getvalue() == 'abcd123'
        t += '\\u1234'
        assert t.getvalue() == 'abcd123\\u1234'
        try:
            t += Broken()
            t.getvalue()
            assert 0
        except BrokenError:
            pass

    def check_text_call(self):
        t = TemplateIO()
        assert t.getvalue() == ''
        t("abcd")
        assert t.getvalue() == 'abcd'
        t(None)
        assert t.getvalue() == 'abcd'
        t(123)
        assert t.getvalue() == 'abcd123'
        t('\\u1234')
        assert t.getvalue() == 'abcd123\\u1234'
        try:
            t(Broken())
            t.getvalue()
            assert 0
        except BrokenError:
            pass

    def check_html_iadd(self):
        t = TemplateIO(html=1)
        assert t.getvalue() == ''
        t += "abcd"
        assert t.getvalue() == 'abcd'
        t += None
        assert t.getvalue() == 'abcd'
        t += 123
        assert t.getvalue() == 'abcd123'
        try:
            t += Broken()
            t.getvalue()
            assert 0
        except BrokenError:
            pass
        t = TemplateIO(html=1)
        t += markupchars
        assert t.getvalue() == quotedchars

    def check_html_call(self):
        t = TemplateIO(html=1)
        assert t.getvalue() == ''
        t("abcd")
        assert t.getvalue() == 'abcd'
        t(None)
        assert t.getvalue() == 'abcd'
        t(123)
        assert t.getvalue() == 'abcd123'
        try:
            t(Broken())
            t.getvalue()
            assert 0
        except BrokenError:
            pass
        t = TemplateIO(html=1)
        t(markupchars)
        assert t.getvalue() == quotedchars

    def check_repr(self):
        t = TemplateIO()
        t += "abcd"
        assert "TemplateIO" in repr(t)

    def check_str(self):
        t = TemplateIO()
        t += "abcd"
        assert str(t) == "abcd"


try:
    from quixote.html import _c_htmltext
except ImportError:
    _c_htmltext = None


def setup_py():
    global htmltext, escape, htmlescape, TemplateIO
    htmltext = _py_htmltext.htmltext
    escape = _py_htmltext._escape_string
    htmlescape = _py_htmltext.htmlescape
    TemplateIO = _py_htmltext.TemplateIO


def setup_c():
    global htmltext, escape, htmlescape, TemplateIO
    htmltext = _c_htmltext.htmltext
    escape = _c_htmltext._escape_string
    htmlescape = _c_htmltext.htmlescape
    TemplateIO = _c_htmltext.TemplateIO


def test_all():
    setup_py()
    HTMLTest()
    HTMLTextTest()
    TemplateTest()
    if _c_htmltext:
        setup_c()
        HTMLTest()
        HTMLTextTest()
        TemplateTest()


if __name__ == "__main__":
    test_all()
