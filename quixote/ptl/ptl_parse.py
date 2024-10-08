"""Parse a PTL template, return AST node.

First h-strings (F-strings that are to become htmltext) are marked.
Next, the file is parsed into a parse tree.  This tree is converted into
a modified AST.  It is during this state that the semantics are modified
by adding extra nodes to the tree.  The modified AST is returned, ready
to pass to the compile() built-in function.
"""

import sys
import io
import ast
import tokenize

# A special marker for h-strings, added as a prefix by token
# translator. It is not allowed to appear in source code literals.
# This is not so elegant but seems the simplist way to pass along the
# information from the tokenizer to the AST that a string should be
# htmltext.
HSTRING_MARKER = '\x02HSTRING\x03'

TEMPLATE_TYPES = {
    'ptl_html': 'html',
    'ptl_plain': 'plain',
}


def _is_h_str_tok(tok):
    """Return True if the token is a h-string (f-string as htmltext)."""
    prefix = tok.string[:2]
    return prefix in {'F"', "F'"}


def _translate_hstrings_lexical(tokens):
    """Find h-string literals and annotate them so that the AST transform
    can turn them into htmltext values.
    """
    # This version handles Python >= 3.12, post PEP 701.

    FSTRING_START = tokenize.FSTRING_START
    FSTRING_MIDDLE = tokenize.FSTRING_MIDDLE
    FSTRING_END = tokenize.FSTRING_END

    # A stack to track if we are currently inside of a h-string.  Since
    # f-strings can be nested, this needs to be a stack and not just a
    # boolean.
    in_h_string = [False]
    i = 0
    while i < len(tokens):
        tok = tokens[i]
        if tok.type == FSTRING_START:
            in_h_string.append(_is_h_str_tok(tokens[i]))
        elif tok.type == FSTRING_END:
            in_h_string.pop()
        if (
            tok.type == FSTRING_START
            and in_h_string[-1]
            and tokens[i + 1].type != FSTRING_MIDDLE
        ):
            # Ensure there is always a FSTRING_MIDDLE token following the
            # FSTRING_START token.  In Python >= 3.12+, an empty f-string
            # has no FSTRING_MIDDLE token.  Also, in the case of nested
            # f-strings, there might be no middle token. Since the code below
            # requires a middle value in order to mark the string as an
            # h-string, insert a middle token with an empty value and the
            # h-string marker.
            new_tok = tokenize.TokenInfo(
                FSTRING_MIDDLE, '', tok.end, tok.end, tok.line
            )
            tokens.insert(i + 1, new_tok)
            assert tokens[i].type == FSTRING_START
            assert tokens[i + 1].type == FSTRING_MIDDLE
        elif tok.type == FSTRING_MIDDLE and in_h_string[-1]:
            # Handle Python 3.12+ F-strings.
            if _has_str_marker(tok):
                raise SyntaxError(
                    'invalid str literal, cannot contain h-string marker'
                )
            # prefix string value with marker
            tok_str = HSTRING_MARKER + tok.string
            new_tok = tokenize.TokenInfo(
                tok.type, tok_str, tok.start, tok.end, tok.line
            )
            # replace FSTRING_MIDDLE token with new token with prefixed value
            tokens[i] = new_tok
        i += 1


def _translate_hstrings_tokenized(tokens):
    """Find h-string literals and annotate them so that the AST transform
    can turn them into htmltext values.
    """
    # This version handles Python < 3.12, pre PEP 701.
    i = 0
    while i < len(tokens):
        tok = tokens[i]
        if tok.type == tokenize.STRING and _is_h_str_tok(tok):
            # For Python < 3.12, h-strings show up as a STRING token.  The
            # value of the token must start with F" or F'
            if i == 0:
                i += 1
                continue
            # found a F-prefixed string
            str_tok = list(tok)
            s = tok[1][1:]  # string value with 'F' stripped
            s = ast.literal_eval(s)
            if _has_str_marker(tok):
                raise SyntaxError(
                    'invalid str literal, cannot contain '
                    'h-string marker, got %r' % s
                )
            # prefix the string value with the marker
            s = HSTRING_MARKER + s
            s = repr(s)
            if '{' in s:
                # h-strings do f-string like evaluation, if the string
                # doesn't contain any f-string braces, just use a normal
                # string as that generates more efficient bytecode
                s = 'f' + s
            str_tok[1] = s
            tokens[i] = tokenize.TokenInfo(*str_tok)
        i += 1


if sys.hexversion > 0x30C0000:
    translate_hstrings = _translate_hstrings_lexical
else:
    translate_hstrings = _translate_hstrings_tokenized


def translate_source(buf, filename='<string>'):
    """
    Since we can't modify the parser in the builtin parser module we
    must do token translation here.  Luckily it does not affect line
    numbers.

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
    ut = tokenize.Untokenizer()
    src = ut.untokenize(tokens)
    return ut.encoding, src


if sys.hexversion > 0x30C0000:

    def _is_str_node(n):
        return isinstance(n, ast.Constant) and isinstance(n.value, str)

    def _has_str_marker(n):
        return _is_str_node(n) and HSTRING_MARKER in n.value

    def _h_str_replace(n):
        return ast.Constant(n.value.replace(HSTRING_MARKER, ''))

    def _ast_const(value):
        return ast.Constant(value)

    def _ast_num(value):
        return ast.Constant(value)

else:

    def _is_str_node(n):
        # Python 3.8 replaces Str with Constant
        return isinstance(n, ast.Str) or (
            isinstance(n, ast.Constant) and isinstance(n.value, str)
        )

    def _has_str_marker(n):
        return _is_str_node(n) and HSTRING_MARKER in n.s

    def _h_str_replace(n):
        return ast.Str(n.s.replace(HSTRING_MARKER, ''))

    def _ast_const(value):
        return ast.NameConstant(value)

    def _ast_num(value):
        return ast.Num(value)


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
        html_imp = ast.ImportFrom(
            module='quixote.html',
            names=[
                ast.alias(name='TemplateIO', asname='_q_TemplateIO'),
                ast.alias(name='htmltext', asname='_q_htmltext'),
                ast.alias(name='_q_join', asname='_q_join'),
                ast.alias(name='_q_format', asname='_q_format'),
            ],
            level=0,
        )
        ast.fix_missing_locations(html_imp)
        vars_imp = ast.ImportFrom(
            module='builtins',
            names=[ast.alias(name='vars', asname='_q_vars')],
            level=0,
        )
        ast.fix_missing_locations(vars_imp)
        ptl_imports = [vars_imp, html_imp]
        # skip __future__ statements
        idx = 0
        for i, stmt in enumerate(node.body):
            if (
                isinstance(stmt, ast.ImportFrom)
                and stmt.module == '__future__'
            ):
                idx = i + 1
        node.body[idx:idx] = ptl_imports
        return self.generic_visit(node)

    def visit_FunctionDef(self, node):
        name = node.name
        template_type = None
        # look for @ptl_html or @ptl_plain decorator
        for dec in node.decorator_list:
            if isinstance(dec, ast.Name):
                if dec.id in TEMPLATE_TYPES:
                    template_type = TEMPLATE_TYPES[dec.id]
        if template_type is None:
            self.__template_type.append(None)
            node = self.generic_visit(node)
        else:
            node.name = name
            self.__template_type.append(template_type)
            node = self.generic_visit(node)

            # _q_output = _q_TemplateIO(template_type == 'html')
            klass = ast.Name(id='_q_TemplateIO', ctx=ast.Load())
            arg = _ast_const(template_type == 'html')
            instance = ast.Call(func=klass, args=[arg], keywords=[])
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
            n = ast.Call(func=n, args=[], keywords=[])
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
            call = ast.Call(func=name, args=[node.value], keywords=[])
            ast.copy_location(call, node)
            expr = ast.Expr(call)
            return ast.copy_location(expr, node)
        return node

    def visit_Constant(self, node, html=False):
        if not _is_str_node(node):
            return node
        if html or _has_str_marker(node):
            # found h-string marker, remove it.  Note that marker can appear
            # within the string if there is a string continued over two lines
            # using backslash.
            s = _h_str_replace(node)
            ast.copy_location(s, node)
            # wrap in call to _q_htmltext
            n = ast.Name(id='_q_htmltext', ctx=ast.Load())
            ast.copy_location(n, node)
            n = ast.Call(func=n, args=[s], keywords=[])
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
            if _has_str_marker(v):
                break  # need to use _q_join()
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
                if v.value == HSTRING_MARKER:
                    # The translate_hstrings() function can insert empty
                    # strings into the values list.  Discard them here as
                    # a small performance optimization.
                    continue
                v = self.visit_Constant(v, html=True)
            else:
                v = self.generic_visit(v)
            values.append(v)
        n = ast.Name(id='_q_join', ctx=ast.Load())
        n = ast.Call(func=n, args=values, keywords=[])
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
        conversion = ast.copy_location(_ast_num(node.conversion), node)
        args = [node.value]
        if node.format_spec is not None:
            args += [conversion, node.format_spec]
        elif node.conversion != -1:
            args += [conversion]
        n = ast.Call(func=n, args=args, keywords=[])
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
    parser.add_argument(
        '--dis',
        '-d',
        default=False,
        action="store_true",
        help="disassemble bytecode",
    )
    parser.add_argument(
        '--ast', '-a', default=False, action="store_true", help="dump AST"
    )
    parser.add_argument('files', nargs='+')
    args = parser.parse_args()
    for fn in args.files:
        with open(fn, 'rb') as fp:
            buf = fp.read()
        tree = parse(buf, fn)
        if args.ast:
            print(pprint(tree))
        if args.dis:
            co = compile(tree, fn, 'exec')
            dis.dis(co)


if __name__ == '__main__':
    main()
