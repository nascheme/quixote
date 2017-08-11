#!/usr/bin/env python
from quixote.ptl.ptl_compile import compile_template
from io import StringIO
from quixote.html import TemplateIO, htmltext, _q_join, _q_format

try:
    compile('f""\n', 'none', 'single')
except SyntaxError:
    HAVE_FSTRINGS = False
else:
    HAVE_FSTRINGS = True


def run_ptl(*source):
    """
    Compile the given lines of source code using the ptl compiler
    and run the resulting compiled code.
    """
    # When the ptl compiler compiles a module, it places _q_TemplateIO
    # and _q_htmltext into the globals of the module.  Here, we don't
    # have a module, but we provide these same globals for eval.
    eval(compile_template(StringIO('\n'.join(source)), 'test'),
         dict(_q_TemplateIO=TemplateIO, _q_htmltext=htmltext,
              _q_join=_q_join, _q_format=_q_format))

def test_html():
    run_ptl(
        'from ptl import htmltext',
        'def f [html] (a):',
        '    "&"',
        '    a',
        'assert type(f(1)) == htmltext',
        'assert f("") == "&"',
        'assert f("&") == "&&amp;"',
        'assert f(htmltext("&")) == "&&"')

def test_plain():
    run_ptl(
        'from ptl import htmltext',
        'def f [plain] (a):',
        '    "&"',
        '    a',
        'assert type(f(1)) == str',
        'assert f("") == "&"',
        'assert f("&") == "&&"',
        'assert f(htmltext("&")) == "&&"',
        'assert type(f(htmltext("&"))) == str')

def test_syntax():
    run_ptl('def f(a):\n    a')
    try:
        run_ptl('def f [] (a):\n    a')
        assert 0
    except SyntaxError as e:
        assert e.lineno == 1
    try:
        run_ptl('def f [HTML] (a):\n    a')
        assert 0
    except SyntaxError as e:
        assert e.lineno == 1


if HAVE_FSTRINGS:
    def test_fstring():
        run_ptl(
            'from ptl import htmltext',
            'def f [html] (a):',
            '    f"x{a}"',
            'assert type(f(1)) == htmltext',
            'assert f("&") == "x&amp;"',
            'assert f(htmltext("&")) == "x&"')

    def test_q_join():
        assert _q_join('x', '&') == 'x&amp;'
        assert _q_join('x', htmltext('&')) == 'x&'

    def test_q_format():
        assert _q_format('&') == '&amp;'
        assert _q_format(htmltext('&')) == '&'
        assert _q_format('a', ord('r')) == "'a'"
        assert _q_format('\xff', ord('r')) == "'\xff'"
        assert _q_format('\xff', ord('a')) == "'\\xff'"
        assert _q_format(1, -1, '_>2') == '_1'
        assert _q_format(1, -1, '_>2') == '_1'
        assert _q_format(64, -1, 'c') == '@'
        assert _q_format(38, -1, 'c') == '&'


if __name__ == "__main__":
    import pytest
    pytest.main([__file__])
