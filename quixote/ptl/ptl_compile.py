#!/www/python/bin/python
"""Compile a PTL template.

First template function names are mangled, noting the template type.
Next, the file is parsed into a parse tree.  This tree is converted into
a modified AST.  It is during this state that the semantics are modified
by adding extra nodes to the tree.  Finally bytecode is generated using
the compiler.
"""

import ast
import sys
import os
import stat
import re
import imp
import marshal
import struct
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
                                                   asname='_q_htmltext')],
                                  level=0)
        ast.fix_missing_locations(html_imp)
        vars_imp = ast.ImportFrom(module='builtins',
                                  names=[ast.alias(name='vars',
                                                   asname='_q_vars')], level=0)
        ast.fix_missing_locations(vars_imp)
        ptl_imports = [vars_imp, html_imp]
        # count __future__ statements
        i = 0
        for stmt in node.body:
            if isinstance(stmt, ast.ImportFrom) and stmt.module == '__future__':
                i += 1
            else:
                break
        node.body[i:i] = ptl_imports
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


PTL_EXT = ".ptl"

def dump(code, filename, fp):
    mtime = os.stat(filename)[stat.ST_MTIME]
    fp.write('\0\0\0\0')
    fp.write(struct.pack('<I', mtime))
    marshal.dump(code, fp)
    fp.flush()
    fp.seek(0)
    fp.write(imp.get_magic())

_compile = compile

def compile_template(input, filename, output=None):
    """(input, filename, output=None) -> code

    Compile an open file.
    If output is not None then the code is written to output.
    The code object is returned.
    """
    node = parse(input.read(), filename)
    code = _compile(node, filename, 'exec')
    if output is not None:
        dump(code, filename, output)
    return code

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
            print('Compiling', filename, '...')
        ok = compile(filename, cfile)

def compile_dir(dir, maxlevels=10, force=0):
    """Byte-compile all PTL modules in the given directory tree.
       (Adapted from compile_dir in Python module: compileall.py)

    Arguments (only dir is required):

    dir:       the directory to byte-compile
    maxlevels: maximum recursion level (default 10)
    force:     if true, force compilation, even if timestamps are up-to-date
    """
    print('Listing', dir, '...')
    try:
        names = os.listdir(dir)
    except os.error:
        print("Can't list", dir)
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
                print('Sorry:', exc_type_name + ':',)
                print(sys.exc_value)
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
        print("no files to compile")
    else:
        for filename in args:
            path, ext = os.path.splitext(filename)
            compile(filename, path + ".pyc")

if __name__ == "__main__":
    main()
