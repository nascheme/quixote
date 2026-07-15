#!/usr/bin/env python3
import sys
from io import StringIO

import pytest

from quixote.html import TemplateIO, _q_format, _q_join, htmltext
from quixote.ptl.ptl_compile import compile_template


def run_ptl(*source: str) -> None:
    """
    Compile the given lines of source code using the ptl compiler
    and run the resulting compiled code.
    """
    source_lines = [
        'from quixote.html import htmltext',
        'from quixote.ptl import ptl_plain, ptl_html',
    ] + list(source)
    # When the ptl compiler compiles a module, it places _q_TemplateIO
    # and _q_htmltext into the globals of the module.  Here, we don't
    # have a module, but we provide these same globals for eval.
    eval(
        compile_template(StringIO('\n'.join(source_lines)), 'test'),
        dict(
            _q_TemplateIO=TemplateIO,
            _q_htmltext=htmltext,
            _q_join=_q_join,
            _q_format=_q_format,
        ),
    )


def test_html() -> None:
    run_ptl(
        '@ptl_html',
        'def f(a):',
        '    F"&"',
        '    a',
        'assert type(f(1)) == htmltext',
        'assert f("") == "&"',
        'assert f("&") == "&&amp;"',
        'assert f(htmltext("&")) == "&&"',
    )


def test_plain() -> None:
    run_ptl(
        '@ptl_plain',
        'def f(a):',
        '    "&"',
        '    a',
        'assert type(f(1)) == str',
        'assert f("") == "&"',
        'assert f("&") == "&&"',
        'assert f(htmltext("&")) == "&&"',
        'assert type(f(htmltext("&"))) == str',
    )


def test_fstring() -> None:
    run_ptl(
        '@ptl_html',
        'def f(a):',
        '    F"x{a}"',
        'assert type(f(1)) == htmltext',
        'assert f("&") == "x&amp;"',
        'assert f(htmltext("&")) == "x&"',
    )


def test_fstring_suffix() -> None:
    run_ptl(
        '@ptl_html',
        'def f(a):',
        '    F"{a}<br />"',
        'assert f("foo") == "foo<br />"',
    )


def test_fstring_nested() -> None:
    if sys.hexversion < 0x030F0000:
        return
    run_ptl(
        '@ptl_html',
        'def f():',
        '    F"{F\'<br />\'}"',
        'assert f() == "<br />"',
    )


def test_q_join() -> None:
    assert _q_join('x', '&') == 'x&amp;'
    assert _q_join('x', htmltext('&')) == 'x&'


def test_q_format() -> None:
    assert _q_format('&') == '&amp;'
    assert _q_format(htmltext('&')) == '&'
    assert _q_format('a', ord('r')) == "'a'"
    assert _q_format('\xff', ord('r')) == "'\xff'"
    assert _q_format('\xff', ord('a')) == "'\\xff'"
    assert _q_format(1, -1, '_>2') == '_1'
    assert _q_format(1, -1, '_>2') == '_1'
    with pytest.raises(ValueError):
        _q_format(64, -1, 'c')
    with pytest.raises(ValueError):
        _q_format(38, -1, 'c')


if __name__ == "__main__":
    pytest.main([__file__])
