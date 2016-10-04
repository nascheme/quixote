#!/usr/bin/env python
from quixote.test.utest import UTest
from quixote.ptl.ptl_compile import compile_template
from io import StringIO
from quixote.html import TemplateIO, htmltext

def run_ptl(*source):
    """
    Compile the given lines of source code using the ptl compiler
    and run the resulting compiled code.
    """
    # When the ptl compiler compiles a module, it places _q_TemplateIO
    # and _q_htmltext into the globals of the module.  Here, we don't
    # have a module, but we provide these same globals for eval.
    eval(compile_template(StringIO('\n'.join(source)), 'test'),
         dict(_q_TemplateIO=TemplateIO, _q_htmltext=htmltext))

class Test (UTest):

    def check_html(self):
        run_ptl(
            'from quixote.html import htmltext',
            'def f [html] (a):',
            '    "&"',
            '    a',
            'assert type(f(1)) == htmltext',
            'assert f("") == "&"',
            'assert f("&") == "&&amp;"',
            'assert f(htmltext("&")) == "&&"')

    def check_plain(self):
        run_ptl(
            'from quixote.html import htmltext',
            'def f [plain] (a):',
            '    "&"',
            '    a',
            'assert type(f(1)) == str',
            'assert f("") == "&"',
            'assert f("&") == "&&"',
            'assert f(htmltext("&")) == "&&"',
            'assert type(f(htmltext("&"))) == str')

    def check_syntax(self):
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

def test_all():
    Test()

if __name__ == "__main__":
    test_all()
