from typing import Any

import pytest

from quixote.html import _py_htmltext, href, nl2br, url_quote, url_with_query

try:
    from string.templatelib import Interpolation, Template

    _HAVE_T_STRING = True
except ImportError:
    _HAVE_T_STRING = False

try:
    from quixote.html import _c_htmltext
except ImportError:
    _c_htmltext = None

markupchars = '<>&"'
quotedchars = '&lt;&gt;&amp;&quot;'
unicodechars = '\u1234'
high_code = '\U000e0030'

# Byte types...
markupbytes = b'<>&"'
quotedbytes = b'&lt;&gt;&amp;&quot;'
bytebytes = b'\x01'


class Wrapper:
    def __init__(self, s: str) -> None:
        self.s = s

    def __repr__(self) -> str:
        return self.s

    def __str__(self) -> str:
        return self.s


class BrokenError(Exception):
    pass


class Broken:
    def __str__(self) -> str:
        raise BrokenError('eieee')

    def __repr__(self) -> str:
        raise BrokenError('eieee')


def _get_impl_ids() -> list[str]:
    ids = ['python']
    if _c_htmltext:
        ids.append('c')
    return ids


def _get_impls() -> list[Any]:
    impls: list[Any] = [_py_htmltext]
    if _c_htmltext:
        impls.append(_c_htmltext)
    return impls


@pytest.fixture(params=_get_impls(), ids=_get_impl_ids())
def impl(request: Any) -> Any:
    """Fixture that yields each htmltext implementation (Python, and C if
    available)."""
    return request.param


@pytest.fixture
def htmltext(impl: Any) -> Any:
    return impl.htmltext


@pytest.fixture
def escape(impl: Any) -> Any:
    return impl._escape_string


@pytest.fixture
def htmlescape(impl: Any) -> Any:
    return impl.htmlescape


@pytest.fixture
def TemplateIO(impl: Any) -> Any:
    return impl.TemplateIO


@pytest.fixture
def htmlformat(impl: Any) -> Any:
    if not _HAVE_T_STRING:
        pytest.skip("t-strings not available")
    return impl.htmlformat


# --- HTML utility tests (not implementation-dependent) ---


class TestHref:
    def test_href(self) -> None:
        assert str(href('/foo/bar', 'bar')) == '<a href="/foo/bar">bar</a>'


class TestUrlWithQuery:
    def test_basic(self) -> None:
        assert str(url_with_query('/f/b', a='1')) == '/f/b?a=1'
        assert (
            str(url_with_query('/f/b', a='1', b='3 4'))
            == '/f/b?a=1&amp;b=3%204'
        )


class TestNl2br:
    def test_nl2br(self) -> None:
        assert str(nl2br('a\nb\nc')) == 'a<br />\nb<br />\nc'


class TestUrlQuote:
    def test_url_quote(self) -> None:
        assert url_quote('abc') == 'abc'
        assert url_quote('a b c') == 'a%20b%20c'
        assert url_quote(None, fallback='abc') == 'abc'


# --- htmltext tests (parametrized over implementations) ---


class TestHTMLTextInit:
    def test_basic(self, htmltext: Any) -> None:
        assert str(htmltext('foo')) == 'foo'
        assert str(htmltext(markupchars)) == markupchars
        assert str(htmltext(unicodechars)) == unicodechars
        assert str(htmltext(str(markupchars))) == markupchars
        assert str(htmltext(None)) == 'None'
        assert str(htmltext(1)) == '1'

    def test_broken(self, htmltext: Any) -> None:
        with pytest.raises(BrokenError):
            htmltext(Broken())


class TestHTMLTextEscape:
    def test_escape(
        self, htmltext: Any, escape: Any, htmlescape: Any
    ) -> None:
        assert htmlescape(markupchars) == quotedchars
        assert isinstance(htmlescape(markupchars), htmltext)
        assert escape(markupchars) == quotedchars
        assert escape(unicodechars) == unicodechars
        assert escape(high_code) == high_code
        assert type(escape(markupchars)) is type(markupchars)
        assert isinstance(escape(markupchars), str)
        assert htmlescape(htmlescape(markupchars)) == quotedchars

    def test_escape_bytes_raises(self, escape: Any) -> None:
        with pytest.raises(TypeError):
            escape(markupbytes)

    def test_escape_int_raises(self, escape: Any) -> None:
        with pytest.raises(TypeError):
            escape(1)


class TestHTMLTextCmp:
    def test_cmp(self, htmltext: Any) -> None:
        s = htmltext("foo")
        assert s == 'foo'
        assert s != 'bar'
        assert s == htmltext('foo')
        assert s != htmltext('bar')
        assert htmltext('\\u1234') == '\\u1234'
        assert htmltext('1') != 1
        assert 1 != s


class TestHTMLTextLen:
    def test_len(self, htmltext: Any, htmlescape: Any) -> None:
        assert len(htmltext('foo')) == 3
        assert len(htmltext(markupchars)) == len(markupchars)
        assert len(htmlescape(markupchars)) == len(quotedchars)


class TestHTMLTextHash:
    def test_hash(self, htmltext: Any, htmlescape: Any) -> None:
        assert hash(htmltext('foo')) == hash('foo')
        assert hash(htmltext(markupchars)) == hash(markupchars)
        assert hash(htmlescape(markupchars)) == hash(quotedchars)


class TestHTMLTextConcat:
    def test_concat(self, htmltext: Any) -> None:
        s = htmltext("foo")
        assert s + 'bar' == "foobar"
        assert 'bar' + s == "barfoo"
        assert s + htmltext('bar') == "foobar"
        assert s + markupchars == "foo" + quotedchars
        assert isinstance(s + markupchars, htmltext)
        assert markupchars + s == quotedchars + "foo"
        assert isinstance(markupchars + s, htmltext)
        assert markupchars + htmltext('') == quotedchars

    def test_concat_int_raises(self, htmltext: Any) -> None:
        s = htmltext("foo")
        with pytest.raises(TypeError):
            s + 1
        with pytest.raises(TypeError):
            1 + s

    def test_concat_repr(self, htmltext: Any) -> None:
        assert repr(htmltext('a') + htmltext('b')) == "<htmltext 'ab'>"


class TestHTMLTextRepeat:
    def test_repeat(self, htmltext: Any, htmlescape: Any) -> None:
        s = htmltext('a')
        assert s * 3 == "aaa"
        assert isinstance(s * 3, htmltext)
        assert htmlescape(markupchars) * 3 == quotedchars * 3

    def test_repeat_type_errors(self, htmltext: Any) -> None:
        s = htmltext('a')
        with pytest.raises(TypeError):
            s * 'a'
        with pytest.raises(TypeError):
            'a' * s
        with pytest.raises(TypeError):
            s * s


class TestHTMLTextFormat:
    def test_format(self, htmltext: Any, htmlescape: Any) -> None:
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
        assert htmltext('%d') % 12300000000000000000 == "12300000000000000000"

    def test_format_broken_raises(self, htmltext: Any) -> None:
        with pytest.raises(BrokenError):
            htmltext('%r') % Broken()


class TestHTMLTextDictFormat:
    def test_dict_format(self, htmltext: Any) -> None:
        args = {'a': 'foo&', 'b': htmltext('bar&')}
        result = "foo&amp; 'foo&amp;' bar&"
        assert htmltext('%(a)s %(a)r %(b)s') % args == result
        assert htmltext('%(a)s') % {'a': 'foo&'} == "foo&amp;"
        assert isinstance(htmltext('%(a)s') % {'a': 'a'}, htmltext)
        assert htmltext('%s') % {'a': 'foo&'} == "{'a': 'foo&amp;'}"
        assert htmltext('') % {} == ''
        assert htmltext('%%') % {} == '%'

    def test_dict_format_type_error(self, htmltext: Any) -> None:
        with pytest.raises(TypeError):
            htmltext('%(a)s') % 1

    def test_dict_format_key_error(self, htmltext: Any) -> None:
        with pytest.raises(KeyError):
            htmltext('%(a)s') % {}


class TestHTMLTextFormatMethod:
    def test_format_method(self, htmltext: Any) -> None:
        assert htmltext('{}').format('foo') == 'foo'
        assert htmltext('{}').format('foo', **{}) == 'foo'
        assert htmltext('{a}').format(a='foo') == 'foo'
        args = {'a': 'foo&', 'b': htmltext('bar&')}
        result = "foo&amp; bar&"
        assert htmltext('{a} {b}').format(**args) == result

    def test_format_method_index_error(self, htmltext: Any) -> None:
        with pytest.raises(IndexError):
            htmltext('{}').format()


class TestHTMLTextJoin:
    def test_join(self, htmltext: Any, htmlescape: Any) -> None:
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

    def test_join_type_errors(self, htmltext: Any) -> None:
        with pytest.raises(TypeError):
            htmltext('').join(1)
        with pytest.raises(TypeError):
            htmltext('').join([1])


class TestHTMLTextStartsWith:
    def test_startswith(self, htmltext: Any, htmlescape: Any) -> None:
        assert htmltext('foo').startswith('fo')
        assert htmlescape(markupchars).startswith(markupchars[:3])
        assert htmltext(markupchars).startswith(htmltext(markupchars[:3]))

    def test_startswith_type_error(self, htmltext: Any) -> None:
        with pytest.raises(TypeError):
            htmltext('').startswith(1)


class TestHTMLTextEndsWith:
    def test_endswith(self, htmltext: Any, htmlescape: Any) -> None:
        assert htmltext('foo').endswith('oo')
        assert htmlescape(markupchars).endswith(markupchars[-3:])
        assert htmltext(markupchars).endswith(htmltext(markupchars[-3:]))

    def test_endswith_type_error(self, htmltext: Any) -> None:
        with pytest.raises(TypeError):
            htmltext('').endswith(1)


class TestHTMLTextReplace:
    def test_replace(self, htmltext: Any, htmlescape: Any) -> None:
        assert htmlescape('&').replace('&', 'foo') == "foo"
        assert htmltext('&').replace(htmltext('&'), 'foo') == "foo"
        assert htmltext('foo').replace('foo', htmltext('&')) == "&"
        assert isinstance(htmltext('a').replace('a', 'b'), htmltext)

    def test_replace_type_error(self, htmltext: Any) -> None:
        with pytest.raises(TypeError):
            htmltext('').replace(1, 'a')


class TestHTMLTextCase:
    def test_lower(self, htmltext: Any) -> None:
        assert htmltext('aB').lower() == "ab"
        assert isinstance(htmltext('a').lower(), htmltext)

    def test_upper(self, htmltext: Any) -> None:
        assert htmltext('aB').upper() == "AB"
        assert isinstance(htmltext('a').upper(), htmltext)

    def test_capitalize(self, htmltext: Any) -> None:
        assert htmltext('aB').capitalize() == "Ab"
        assert isinstance(htmltext('a').capitalize(), htmltext)


# --- TemplateIO tests ---


class TestTemplateIOInit:
    def test_init(self, TemplateIO: Any) -> None:
        TemplateIO()
        TemplateIO(html=True)
        TemplateIO(html=False)


class TestTemplateIOTextIadd:
    def test_text_iadd(self, TemplateIO: Any) -> None:
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

    def test_text_iadd_broken(self, TemplateIO: Any) -> None:
        t = TemplateIO()
        with pytest.raises(BrokenError):
            t += Broken()
            t.getvalue()


class TestTemplateIOTextCall:
    def test_text_call(self, TemplateIO: Any) -> None:
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

    def test_text_call_broken(self, TemplateIO: Any) -> None:
        t = TemplateIO()
        with pytest.raises(BrokenError):
            t(Broken())
            t.getvalue()


class TestTemplateIOHtmlIadd:
    def test_html_iadd(self, TemplateIO: Any) -> None:
        t = TemplateIO(html=1)
        assert t.getvalue() == ''
        t += "abcd"
        assert t.getvalue() == 'abcd'
        t += None
        assert t.getvalue() == 'abcd'
        t += 123
        assert t.getvalue() == 'abcd123'

    def test_html_iadd_broken(self, TemplateIO: Any) -> None:
        t = TemplateIO(html=1)
        with pytest.raises(BrokenError):
            t += Broken()
            t.getvalue()

    def test_html_iadd_markup(self, TemplateIO: Any) -> None:
        t = TemplateIO(html=1)
        t += markupchars
        assert t.getvalue() == quotedchars


class TestTemplateIOHtmlCall:
    def test_html_call(self, TemplateIO: Any) -> None:
        t = TemplateIO(html=1)
        assert t.getvalue() == ''
        t("abcd")
        assert t.getvalue() == 'abcd'
        t(None)
        assert t.getvalue() == 'abcd'
        t(123)
        assert t.getvalue() == 'abcd123'

    def test_html_call_broken(self, TemplateIO: Any) -> None:
        t = TemplateIO(html=1)
        with pytest.raises(BrokenError):
            t(Broken())
            t.getvalue()

    def test_html_call_markup(self, TemplateIO: Any) -> None:
        t = TemplateIO(html=1)
        t(markupchars)
        assert t.getvalue() == quotedchars


class TestTemplateIORepr:
    def test_repr(self, TemplateIO: Any) -> None:
        t = TemplateIO()
        t += "abcd"
        assert "TemplateIO" in repr(t)


class TestTemplateIOStr:
    def test_str(self, TemplateIO: Any) -> None:
        t = TemplateIO()
        t += "abcd"
        assert str(t) == "abcd"


# --- htmlformat (t-string) tests ---


if _HAVE_T_STRING:

    def _interp(value: Any, format_spec: str = "") -> Any:
        """Helper to create an Interpolation with no conversion."""
        return Interpolation(value, "value", None, format_spec)

    class TestHTMLFormat:
        def test_basic_literal(self, htmltext: Any, htmlformat: Any) -> None:
            t = Template("hello")
            result = htmlformat(t)
            assert isinstance(result, htmltext)
            assert str(result) == "hello"

        def test_literal_with_markup(
            self, htmltext: Any, htmlformat: Any
        ) -> None:
            t = Template("<b>bold</b>")
            result = htmlformat(t)
            assert isinstance(result, htmltext)
            assert str(result) == "<b>bold</b>"

        def test_string_interpolation_escaped(
            self, htmltext: Any, htmlformat: Any
        ) -> None:
            t = Template("hello ", _interp(markupchars), " world")
            result = htmlformat(t)
            assert isinstance(result, htmltext)
            assert str(result) == "hello " + quotedchars + " world"

        def test_htmltext_interpolation_not_escaped(
            self, htmltext: Any, htmlformat: Any
        ) -> None:
            safe = htmltext("<b>bold</b>")
            t = Template("hello ", _interp(safe), " world")
            result = htmlformat(t)
            assert isinstance(result, htmltext)
            assert str(result) == "hello <b>bold</b> world"

        def test_int_interpolation(
            self, htmltext: Any, htmlformat: Any
        ) -> None:
            t = Template("count: ", _interp(42), "")
            result = htmlformat(t)
            assert isinstance(result, htmltext)
            assert str(result) == "count: 42"

        def test_float_interpolation(
            self, htmltext: Any, htmlformat: Any
        ) -> None:
            t = Template("val: ", _interp(3.14), "")
            result = htmlformat(t)
            assert isinstance(result, htmltext)
            assert str(result) == "val: 3.14"

        def test_format_spec(self, htmlformat: Any) -> None:
            t = Template("val: ", _interp(3.14159, ".2f"), "")
            result = htmlformat(t)
            assert str(result) == "val: 3.14"

        def test_format_spec_string(
            self, htmltext: Any, htmlformat: Any
        ) -> None:
            t = Template("x", _interp("a&b", "s"), "x")
            result = htmlformat(t)
            assert isinstance(result, htmltext)
            assert str(result) == "xa&amp;bx"

        def test_object_interpolation_escaped(
            self, htmltext: Any, htmlformat: Any
        ) -> None:
            t = Template("", _interp(Wrapper(markupchars)), "")
            result = htmlformat(t)
            assert isinstance(result, htmltext)
            assert str(result) == quotedchars

        def test_conversion_raises(self, htmlformat: Any) -> None:
            interp = Interpolation("foo", "value", "s", "")
            t = Template("", interp, "")
            with pytest.raises(ValueError):
                htmlformat(t)

        def test_non_template_raises(self, htmlformat: Any) -> None:
            with pytest.raises(TypeError):
                htmlformat("not a template")

        def test_empty_template(self, htmltext: Any, htmlformat: Any) -> None:
            t = Template("")
            result = htmlformat(t)
            assert isinstance(result, htmltext)
            assert str(result) == ""

        def test_multiple_interpolations(
            self, htmltext: Any, htmlformat: Any
        ) -> None:
            t = Template(
                "<p>",
                _interp("a&b"),
                " and ",
                _interp(htmltext("<em>safe</em>")),
                "</p>",
            )
            result = htmlformat(t)
            assert isinstance(result, htmltext)
            assert str(result) == "<p>a&amp;b and <em>safe</em></p>"
