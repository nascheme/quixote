"""Parse a PTL template, return AST node.

First template function names are mangled, noting the template type.
Next, the file is parsed into a parse tree.  This tree is converted into
a modified AST.  It is during this state that the semantics are modified
by adding extra nodes to the tree.  The modified AST is returned, ready
to pass to the compile() built-in function.
"""

import sys
import re
import io
import ast
import tokenize

# special marker for h-strings, cannot appear in source code literals
HSTRING_MARKER = 'HSTRING\xa0\x00'

TEMPLATE_TYPES = {
    'ptl_html': 'html',
    'ptl_plain': 'plain',
}

def translate_defs(tokens):
    # Rename the function name for html/plain templates.  The special names
    # will be recognized by the AST transformer.
    NAME = tokenize.NAME
    OP = tokenize.OP
    i = 0
    while i < len(tokens):
        tok = tokens[i]
        if tok.type == NAME and tok.string == 'def':
            if (tokens[i+2][:2] == (OP, '[') and
                tokens[i+4][:2] == (OP, ']')):
                name_tok = list(tokens[i+1])
                prefix = '_q_%s_template_' % tokens[i+3].string
                name_tok[1] = prefix + name_tok[1]
                del tokens[i+2:i+5]
                tokens[i+1] = tokenize.TokenInfo(*name_tok)
        i += 1


def translate_hstrings(tokens):
    # Detect h-string literals.  They should up in the token stream
    # as two tokens, e.g. h"foo":
    #   NAME    'h'
    #   STRING  '"foo"'
    #
    # We translate them to:
    #
    #   STRING f'"<HSTRING_PREFIX>foo"'
    #
    # The AST transformer will detect the prefix and wrap them in
    # calls of htmltext().
    STRING = tokenize.STRING
    NAME = tokenize.NAME
    i = 0
    while i < len(tokens):
        tok = tokens[i]
        if tok.type == STRING:
            if i == 0:
                i += 1
                continue
            need_dedent = False
            prefix = tok.string[:2]
            if prefix in {'F"', "F'"}:
                # found a F-prefixed string
                have_h_string = True
                str_tok = list(tok)
                s = tok[1][1:] # string value with 'F' stripped
            elif tokens[i-1].type == NAME and tokens[i-1].string == 'h':
                # found a h-prefixed string
                have_h_string = True
                str_tok = list(tokens[i])
                s = str_tok[1]
                # h prefix is separate token, remove it
                del tokens[i-1]
                i -= 1
                need_dedent = True
            else:
                have_h_string = False
            if have_h_string:
                s = ast.literal_eval(s)
                if HSTRING_MARKER in s:
                    raise SyntaxError('invalid str literal, cannot contain '
                                      'h-string marker, got %r' % s)
                # prefix string with marker.  Putting the marker inside the
                # string is not so elegant but it is an easy way to pass
                # the annotation along to the AST transformer.  The check
                # above ensures that no real string contains the marker.
                s = HSTRING_MARKER + s
                s = repr(s)
                if '{' in s:
                    # h-strings do f-string like evaluation, if the string
                    # doesn't contain any f-string braces, just use a normal
                    # string as that generates more efficient bytecode
                    s = 'f' + s
                str_tok[1] = s
                if need_dedent:
                    # deindent one character, we stripped (NAME 'h') token
                    srow, scol = str_tok[2]
                    str_tok[2] = (srow, scol-1)
                tokens[i] = tokenize.TokenInfo(*str_tok)
        i += 1


def translate_source(buf, filename='<string>'):
    """
    Since we can't modify the parser in the builtin parser module we
    must do token translation here.  Luckily it does not affect line
    numbers.

    def foo [plain] (...): -> def _q_plain_template__foo(...):

    def foo [html] (...): -> def _q_html_template__foo(...):

    h'foo' -> f'<HSTRING_PREFIX>foo'
    F'foo' -> f'<HSTRING_PREFIX>foo'
    """
    assert isinstance(buf, bytes)
    fp = io.BytesIO(buf)
    try:
        tokens = list(tokenize.tokenize(fp.readline))
    except SyntaxError as exc:
        exc_type = type(exc)
        raise exc_type(str(exc), (filename, exc.lineno, exc.offset, exc.text))
    translate_hstrings(tokens)
    translate_defs(tokens)
    ut = tokenize.Untokenizer()
    src = ut.untokenize(tokens)
    return ut.encoding, src


def _is_str_node(n):
    # Python 3.8 replaces Str with Constant
    return (isinstance(n, ast.Str) or
            (isinstance(n, ast.Constant) and isinstance(n.value, str)))


class TemplateTransformer(ast.NodeTransformer):
    def __init__(self, *args, **kwargs):
        ast.NodeTransformer.__init__(self, *args, **kwargs)
        # __template_type is a stack whose values are
        # "html", "plain", or None
        self.__template_type = [None]

    def _get_template_type(self):
        """Return the type of the function being compiled (
        "html", "plain", or None)
        """
        if self.__template_type:
            return self.__template_type[-1]
        else:
            return None

    def visit_Module(self, node):
        html_imp = ast.ImportFrom(module='quixote.html',
                                  names=[ast.alias(name='TemplateIO',
                                                   asname='_q_TemplateIO'),
                                         ast.alias(name='htmltext',
                                                   asname='_q_htmltext'),
                                         ast.alias(name='_q_join',
                                                   asname='_q_join'),
                                         ast.alias(name='_q_format',
                                                   asname='_q_format'),
                                         ],
                                  level=0)
        ast.fix_missing_locations(html_imp)
        vars_imp = ast.ImportFrom(module='builtins',
                                  names=[ast.alias(name='vars',
                                                   asname='_q_vars')], level=0)
        ast.fix_missing_locations(vars_imp)
        ptl_imports = [vars_imp, html_imp]
        # skip __future__ statements
        idx = 0
        for i, stmt in enumerate(node.body):
            if isinstance(stmt, ast.ImportFrom) and stmt.module == '__future__':
                idx = i + 1
        node.body[idx:idx] = ptl_imports
        return self.generic_visit(node)

    def visit_FunctionDef(self, node):
        name = node.name
        template_type = None
        # look for @html or @plain decorator
        for dec in node.decorator_list:
            if isinstance(dec, ast.Name):
                if dec.id in TEMPLATE_TYPES:
                    template_type = TEMPLATE_TYPES[dec.id]
        if template_type is None:
            # look for old-style [html] or [plain] annotation
            m = re.match('_q_(html|plain)_template_(.*)', name)
            if m:
                template_type = m.group(1)
                name = m.group(2)
        if template_type is None:
            self.__template_type.append(None)
            node = self.generic_visit(node)
        else:
            node.name = name
            self.__template_type.append(template_type)
            node = self.generic_visit(node)

            # _q_output = _q_TemplateIO(template_type == 'html')
            klass = ast.Name(id='_q_TemplateIO', ctx=ast.Load())
            arg = ast.NameConstant(template_type == 'html')
            instance = ast.Call(func=klass, args=[arg], keywords=[],
                                starargs=None, kwargs=None)
            assign_name = ast.Name(id='_q_output', ctx=ast.Store())
            assign = ast.Assign(targets=[assign_name], value=instance)
            ast.copy_location(assign, node)
            ast.fix_missing_locations(assign)
            docstring = getattr(node, 'docstring', None)
            if docstring:
                # Python 3.7 alpha adds a docstring attribute to FunctionDef
                # bpo-29463: Add docstring field to some AST nodes. (#46)
                docstring = ast.Expr(ast.Str(docstring))
                ast.copy_location(assign, docstring)
                ast.fix_missing_locations(docstring)
                node.body.insert(0, self.visit_Expr(docstring))
                node.docstring = ''
            node.body.insert(0, assign)

            # return _q_output.getvalue()
            n = ast.Name(id='_q_output', ctx=ast.Load())
            n = ast.Attribute(value=n, attr='getvalue', ctx=ast.Load())
            n = ast.Call(func=n, args=[], keywords=[], starargs=None,
                         kwargs=None)
            ret = ast.Return(value=n)
            ast.copy_location(ret, node.body[-1])
            ast.fix_missing_locations(ret)
            node.body.append(ret)

        self.__template_type.pop()
        return node

    def visit_Expr(self, node):
        node = self.generic_visit(node)
        if self._get_template_type() is not None:
            # Inside template function.  Instead of discarding objects on the
            # stack, call _q_output(obj).
            name = ast.Name(id='_q_output', ctx=ast.Load())
            ast.copy_location(name, node)
            call = ast.Call(func=name, args=[node.value], keywords=[],
                            starargs=None, kwargs=None)
            ast.copy_location(call, node)
            expr = ast.Expr(call)
            return ast.copy_location(expr, node)
        return node

    def visit_Constant(self, node, html=False):
        if not _is_str_node(node):
            return node
        if html or HSTRING_MARKER in node.s:
            # found h-string marker, remove it.  Note that marker can appear
            # within the string if there is a string continued over two lines
            # using backslash.
            s = ast.Str(node.s.replace(HSTRING_MARKER, ''))
            ast.copy_location(s, node)
            # wrap in call to _q_htmltext
            n = ast.Name(id='_q_htmltext', ctx=ast.Load())
            ast.copy_location(n, node)
            n = ast.Call(func=n, args=[s], keywords=[], starargs=None,
                         kwargs=None)
            return ast.copy_location(n, node)
        return node

    def visit_Str(self, node, html=False):
        # exists for backwards compatibility, Python 3.8 uses Constant
        return self.visit_Constant(node, html=html)

    def visit_JoinedStr(self, node):
        # JoinedStr is used for combining the parts of an f-string.
        # In CPython, it is done with the BUILD_STRING opcode.  For
        # h-strings, we call quixote.html._q_join() instead.
        for v in node.values:
            if _is_str_node(v) and HSTRING_MARKER in v.s:
                break # need to use _q_join()
        else:
            # none of the join arguments are htmltext, just use normal
            # f-string logic
            return self.generic_visit(node)
        # call _q_format on the values, call _q_join to create the result
        values = []
        for v in node.values:
            if isinstance(v, ast.FormattedValue):
                v = self.visit_FormattedValue(v, html=True)
            elif _is_str_node(v):
                v = self.visit_Constant(v, html=True)
            else:
                v = self.generic_visit(v)
            values.append(v)
        n = ast.Name(id='_q_join', ctx=ast.Load())
        n = ast.Call(func=n, args=values, keywords=[],
                     starargs=None,
                     kwargs=None)
        ast.copy_location(n, node)
        ast.fix_missing_locations(n)
        return n

    def visit_FormattedValue(self, node, html=False):
        # FormattedValue is used for the {..} parts of an f-string.
        # In CPython, there is a FORMAT_VALUE opcode.  For h-strings
        # call quixote.html._q_format instead.
        node = self.generic_visit(node)
        if not html:
            return node
        n = ast.Name(id='_q_format', ctx=ast.Load())
        conversion = ast.copy_location(ast.Num(node.conversion), node)
        args = [node.value]
        if node.format_spec is not None:
            args += [conversion, node.format_spec]
        elif node.conversion != -1:
            args += [conversion]
        n = ast.Call(func=n, args=args,
                     keywords=[],
                     starargs=None,
                     kwargs=None)
        ast.copy_location(n, node)
        ast.fix_missing_locations(n)
        return n


def translate_ast(node):
    t = TemplateTransformer()
    return t.visit(node)


def parse(buf, filename='<string>'):
    if isinstance(buf, str):
        buf = buf.encode('utf-8')
    encoding, buf = translate_source(buf, filename)
    try:
        node = ast.parse(buf, filename)
    except SyntaxError as e:
        # set the filename attribute
        raise SyntaxError(str(e), (filename, e.lineno, e.offset, e.text))
    return translate_ast(node)


def main():
    import argparse
    import dis
    try:
        from astpretty import pprint
    except ImportError:
        pprint = ast.dump
    parser = argparse.ArgumentParser()
    parser.add_argument('--dis', '-d', default=False,
                        action="store_true",
                        help="disassemble bytecode")
    parser.add_argument('--ast', '-a', default=False,
                        action="store_true",
                        help="dump AST")
    parser.add_argument('files', nargs='+')
    args = parser.parse_args()
    for fn in args.files:
        with open(fn, 'rb') as fp:
            buf = fp.read()
        tree = parse(buf, fn)
        if args.ast:
            pprint(tree)
        if args.dis:
            co = compile(tree, fn, 'exec')
            dis.dis(co)

if __name__ == '__main__':
    main()
