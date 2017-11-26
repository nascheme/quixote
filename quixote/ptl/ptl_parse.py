"""Parse a PTL template, return AST node.

First template function names are mangled, noting the template type.
Next, the file is parsed into a parse tree.  This tree is converted into
a modified AST.  It is during this state that the semantics are modified
by adding extra nodes to the tree.  The modified AST is returned, ready
to pass to the compile() built-in function.
"""

import ast
import re
import importlib.util

HTML_TEMPLATE_PREFIX = "_q_html_template_"
PLAIN_TEMPLATE_PREFIX = "_q_plain_template_"

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
        if not re.match('_q_(html|plain)_template_', name):
            # just a normal function
            self.__template_type.append(None)
            node = self.generic_visit(node)
        else:
            if name.startswith(PLAIN_TEMPLATE_PREFIX):
                node.name = name[len(PLAIN_TEMPLATE_PREFIX):]
                template_type = "plain"
            elif name.startswith(HTML_TEMPLATE_PREFIX):
                node.name = name[len(HTML_TEMPLATE_PREFIX):]
                template_type = "html"
            else:
                raise RuntimeError('unknown prefix on %s' % name)

            self.__template_type.append(template_type)
            node = self.generic_visit(node)

            # _q_output = _q_TemplateIO()
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
                # Python 3.7 adds a docstring attribute to FunctionDef
                # bpo-29463: Add docstring field to some AST nodes. (#46)
                docstring = ast.Expr(ast.Str(docstring))
                ast.copy_location(assign, docstring)
                ast.fix_missing_locations(docstring)
                node.body.insert(0, self.visit_Expr(docstring))
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
        if self._get_template_type() is not None:
            node = self.generic_visit(node)
            # Instead of discarding objects on the stack, call
            # "_q_output += obj".
            lval = ast.Name(id='_q_output', ctx=ast.Store())
            ast.copy_location(lval, node)
            aug = ast.AugAssign(target=lval, op=ast.Add(), value=node.value)
            return ast.copy_location(aug, node)
        else:
            return node

    def visit_Str(self, node):
        if "html" == self._get_template_type():
            n = ast.Name(id='_q_htmltext', ctx=ast.Load())
            ast.copy_location(n, node)
            n = ast.Call(func=n, args=[node], keywords=[], starargs=None,
                         kwargs=None)
            return ast.copy_location(n, node)
        else:
            return node

    def visit_JoinedStr(self, node):
        # JoinedStr is used for combining the parts of an f-string.
        # In CPython, it is done with the BUILD_STRING opcode.  We
        # call quixote.html._q_join() instead
        node = self.generic_visit(node)
        if "html" == self._get_template_type():
            n = ast.Name(id='_q_join', ctx=ast.Load())
            n = ast.Call(func=n, args=node.values, keywords=[],
                         starargs=None,
                         kwargs=None)
            ast.copy_location(n, node)
            ast.fix_missing_locations(n)
            return n
        else:
            return node

    def visit_FormattedValue(self, node):
        # FormattedValue is used for the {..} parts of an f-string.
        # In CPython, there is a FORMAT_VALUE opcode.  We call
        # quixote.html._q_format instead.
        node = self.generic_visit(node)
        if "html" == self._get_template_type():
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
        else:
            return node


_template_re = re.compile(r'''
    ^(?P<indent>[ \t]*) def (?:[ \t]+)
    (?P<name>[a-zA-Z_][a-zA-Z_0-9]*)
    (?:[ \t]*) \[(?P<type>plain|html)\] (?:[ \t]*)
    (?:[ \t]*[\(\\])
    ''', re.MULTILINE|re.VERBOSE)

def translate_tokens(buf):
    """
    Since we can't modify the parser in the builtin parser module we
    must do token translation here.  Luckily it does not affect line
    numbers.

    def foo [plain] (...): -> def _q_plain_template__foo(...):

    def foo [html] (...): -> def _q_html_template__foo(...):

    XXX This parser is too stupid.  For example, it doesn't understand
    triple quoted strings.
    """
    def replacement(match):
        template_type = match.group('type')
        return '%sdef _q_%s_template_%s(' % (match.group('indent'),
                                             template_type,
                                             match.group('name'))
    return  _template_re.sub(replacement, buf)

def parse(buf, filename='<string>'):
    if isinstance(buf, bytes):
        buf = importlib.util.decode_source(buf)
    buf = translate_tokens(buf)
    try:
        node = ast.parse(buf, filename)
    except SyntaxError as e:
        # set the filename attribute
        raise SyntaxError(str(e), (filename, e.lineno, e.offset, e.text))
    t = TemplateTransformer()
    return t.visit(node)
