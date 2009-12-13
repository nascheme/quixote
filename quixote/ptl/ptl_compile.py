#!/www/python/bin/python
"""Compile a PTL template.

First template function names are mangled, noting the template type.
Next, the file is parsed into a parse tree.  This tree is converted into
a modified AST.  It is during this state that the semantics are modified
by adding extra nodes to the tree.  Finally bytecode is generated using
the compiler package.
"""

import sys
import os
import stat
import symbol
import token
import re
import imp
import stat
import marshal
import struct

assert sys.hexversion >= 0x20300b1, 'PTL requires Python 2.3 or newer'

from compiler import pycodegen, transformer
from compiler import ast
from compiler.consts import OP_ASSIGN
from compiler import misc, syntax

HTML_TEMPLATE_PREFIX = "_q_html_template_"
PLAIN_TEMPLATE_PREFIX = "_q_plain_template_"

class TemplateTransformer(transformer.Transformer):

    def __init__(self, *args, **kwargs):
        transformer.Transformer.__init__(self, *args, **kwargs)
        # __template_type is a stack whose values are
        # "html", "plain", or None
        self.__template_type = []

    def _get_template_type(self):
        """Return the type of the function being compiled (
        "html", "plain", or None)
        """
        if self.__template_type:
            return self.__template_type[-1]
        else:
            return None

    def file_input(self, nodelist):
        doc = None # self.get_docstring(nodelist, symbol.file_input)
        if sys.hexversion >= 0x02050000:
            html_imp = ast.From(
                'quixote.html',
                [('TemplateIO', '_q_TemplateIO'), ('htmltext', '_q_htmltext')],
                0)
            vars_imp = ast.From("__builtin__", [("vars", "_q_vars")], 0)
        else:
            html_imp = ast.From(
                'quixote.html',
                [('TemplateIO', '_q_TemplateIO'), ('htmltext', '_q_htmltext')])
            vars_imp = ast.From("__builtin__", [("vars", "_q_vars")])

        ptl_imports = [ vars_imp, html_imp ]
        stmts = []
        for node in nodelist:
            if node[0] != token.ENDMARKER and node[0] != token.NEWLINE:
                self.com_append_stmt(stmts, node)
        # count __future__ statements
        i = 0
        for stmt in stmts:
            if isinstance(stmt, ast.From) and stmt.modname == '__future__':
                i += 1
            else:
                break
        stmts[i:i] = ptl_imports
        return ast.Module(doc, ast.Stmt(stmts))

    def funcdef(self, nodelist):
        if len(nodelist) == 6:
            assert nodelist[0][0] == symbol.decorators
            decorators = self.decorators(nodelist[0][1:])
        else:
            assert len(nodelist) == 5
            decorators = None

        lineno = nodelist[-4][2]
        name = nodelist[-4][1]
        args = nodelist[-3][2]

        if not re.match('_q_(html|plain)_(dollar_)?template_', name):
            # just a normal function, let base class handle it
            self.__template_type.append(None)
            n = transformer.Transformer.funcdef(self, nodelist)
        else:
            if name.startswith(PLAIN_TEMPLATE_PREFIX):
                name = name[len(PLAIN_TEMPLATE_PREFIX):]
                template_type = "plain"
            elif name.startswith(HTML_TEMPLATE_PREFIX):
                name = name[len(HTML_TEMPLATE_PREFIX):]
                template_type = "html"
            else:
                raise RuntimeError, 'unknown prefix on %s' % name

            self.__template_type.append(template_type)

            if args[0] == symbol.varargslist:
                names, defaults, flags = self.com_arglist(args[1:])
            else:
                names = defaults = ()
                flags = 0
            doc = None # self.get_docstring(nodelist[-1])

            # code for function
            code = self.com_node(nodelist[-1])

            # _q_output = _q_TemplateIO()
            klass = ast.Name('_q_TemplateIO')
            args = [ast.Const(template_type == "html")]
            instance = ast.CallFunc(klass, args)
            assign_name = ast.AssName('_q_output', OP_ASSIGN)
            assign = ast.Assign([assign_name], instance)

            # return _q_output.getvalue()
            func = ast.Getattr(ast.Name('_q_output'), "getvalue")
            ret = ast.Return(ast.CallFunc(func, []))

            # wrap original function code
            code = ast.Stmt([assign, code, ret])

            if sys.hexversion >= 0x20400a2:
                n = ast.Function(decorators, name, names, defaults, flags, doc,
                                 code)
            else:
                n = ast.Function(name, names, defaults, flags, doc, code)
            n.lineno = lineno

        self.__template_type.pop()
        return n

    def expr_stmt(self, nodelist):
        if self._get_template_type() is None:
            return transformer.Transformer.expr_stmt(self, nodelist)

        # Instead of discarding objects on the stack, call
        # "_q_output += obj".
        exprNode = self.com_node(nodelist[-1])
        if len(nodelist) == 1:
            lval = ast.Name('_q_output')
            n = ast.AugAssign(lval, '+=', exprNode)
            if hasattr(exprNode, 'lineno'):
                n.lineno = exprNode.lineno
        elif nodelist[1][0] == token.EQUAL:
            nodes = [ ]
            for i in range(0, len(nodelist) - 2, 2):
                nodes.append(self.com_assign(nodelist[i], OP_ASSIGN))
            n = ast.Assign(nodes, exprNode)
            n.lineno = nodelist[1][2]
        else:
            lval = self.com_augassign(nodelist[0])
            op = self.com_augassign_op(nodelist[1])
            n = ast.AugAssign(lval, op[1], exprNode)
            n.lineno = op[2]
        return n

    def atom_string(self, nodelist):
        const_node = transformer.Transformer.atom_string(self, nodelist)
        if "html" == self._get_template_type():
            return ast.CallFunc(ast.Name('_q_htmltext'), [const_node])
        else:
            return const_node

_template_re = re.compile(
    r"^(?P<indent>[ \t]*) def (?:[ \t]+)"
    r" (?P<name>[a-zA-Z_][a-zA-Z_0-9]*)"
    r" (?:[ \t]*) \[(?P<type>plain|html)\] (?:[ \t]*)"
    r" (?:[ \t]*[\(\\])",
    re.MULTILINE|re.VERBOSE)

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
    buf = translate_tokens(buf)
    try:
        return TemplateTransformer().parsesuite(buf)
    except SyntaxError, e:
        # set the filename attribute
        raise SyntaxError(str(e), (filename, e.lineno, e.offset, e.text))


PTL_EXT = ".ptl"

class Template(pycodegen.Module):

    def _get_tree(self):
        tree = parse(self.source, self.filename)
        misc.set_filename(self.filename, tree)
        syntax.check(tree)
        return tree

    def dump(self, fp):
        mtime = os.stat(self.filename)[stat.ST_MTIME]
        fp.write('\0\0\0\0')
        fp.write(struct.pack('<I', mtime))
        marshal.dump(self.code, fp)
        fp.flush()
        fp.seek(0)
        fp.write(imp.get_magic())


def compile_template(input, filename, output=None):
    """(input, filename, output=None) -> code

    Compile an open file.
    If output is not None then the code is written to output.
    The code object is returned.
    """
    buf = input.read()
    template = Template(buf, filename)
    template.compile()
    if output is not None:
        template.dump(output)
    return template.code

def compile(inputname, outputname):
    """(inputname, outputname)

    Compile a template file.  The new template is written to outputname.
    """
    input = open(inputname)
    output = open(outputname, "wb")
    try:
        compile_template(input, inputname, output)
    except:
        # don't leave a corrupt .pyc file around
        output.close()
        os.unlink(outputname)
        raise

def compile_file(filename, force=0, verbose=0):
    if filename.endswith(PTL_EXT):
        cfile = filename[:-4] + '.pyc'
        ftime = os.stat(filename)[stat.ST_MTIME]
        try:
            ctime = os.stat(cfile)[stat.ST_MTIME]
        except os.error:
            ctime = 0
        if (ctime > ftime) and not force:
            return
        if verbose:
            print 'Compiling', filename, '...'
        ok = compile(filename, cfile)

def compile_dir(dir, maxlevels=10, force=0):
    """Byte-compile all PTL modules in the given directory tree.
       (Adapted from compile_dir in Python module: compileall.py)

    Arguments (only dir is required):

    dir:       the directory to byte-compile
    maxlevels: maximum recursion level (default 10)
    force:     if true, force compilation, even if timestamps are up-to-date
    """
    print 'Listing', dir, '...'
    try:
        names = os.listdir(dir)
    except os.error:
        print "Can't list", dir
        names = []
    names.sort()
    success = 1
    for name in names:
        fullname = os.path.join(dir, name)
        if os.path.isfile(fullname):
            try:
                ok = compile_file(fullname, force=force, verbose=1)
            except KeyboardInterrupt:
                raise KeyboardInterrupt
            except:
                # XXX compile catches SyntaxErrors
                if type(sys.exc_type) == type(''):
                    exc_type_name = sys.exc_type
                else: exc_type_name = sys.exc_type.__name__
                print 'Sorry:', exc_type_name + ':',
                print sys.exc_value
                success = 0
            else:
                if ok == 0:
                    success = 0
        elif (maxlevels > 0 and name != os.curdir and name != os.pardir and
              os.path.isdir(fullname) and not os.path.islink(fullname)):
            if not compile_dir(fullname, maxlevels - 1, force):
                success = 0
    return success

def compile_package(path, force=0, verbose=0):
    """Compile all PTL files in a package.  'path' should be a list
    of directory names containing the files of the package (i.e. __path__).
    """
    for package_dir in path:
        for dirpath, dirnames, filenames in os.walk(package_dir):
            for dirname in dirnames:
                compile_file(os.path.join(dirpath, dirname), force=force,
                             verbose=verbose)
            for filename in filenames:
                compile_file(os.path.join(dirpath, filename), force=force,
                             verbose=verbose)

def main():
    args = sys.argv[1:]
    if not args:
        print "no files to compile"
    else:
        for filename in args:
            path, ext = os.path.splitext(filename)
            compile(filename, path + ".pyc")

if __name__ == "__main__":
    main()
