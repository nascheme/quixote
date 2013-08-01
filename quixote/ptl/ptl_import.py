"""Import hooks; when installed, these hooks allow importing .ptl files
as if they were Python modules.

Note: there's some unpleasant incompatibility between ZODB's import
trickery and the import hooks here.  Bottom line: if you're using ZODB,
import it *before* installing the PTL import hooks.
"""

import sys
import os.path
import imp, ihooks, new
import struct
import marshal
import __builtin__

# Check for a deficient ihooks module.  Python 2.6 was released without
# ihooks.py being updated to support relative imports. Any library that uses
# relative imports will cause the import hook to fail.  Use our local copy of
# ihooks module which does have support for relative imports.
if sys.hexversion >= 0x20600b0:
    _m = ihooks.ModuleImporter.import_module
    if _m.im_func.func_code.co_argcount == 5:
        import ihooks_local as ihooks

from quixote.ptl.ptl_compile import compile_template, PTL_EXT

assert sys.hexversion >= 0x20000b1, "need Python 2.0b1 or later"

def _exec_module_code(code, name, filename):
    if name in sys.modules:
        mod = sys.modules[name] # necessary for reload()
    else:
        mod = new.module(name)
        sys.modules[name] = mod
    mod.__name__ = name
    mod.__file__ = filename
    exec code in mod.__dict__
    return mod

def _timestamp(filename):
    try:
        s = os.stat(filename)
    except OSError:
        return None
    return int(s.st_mtime) & 0xffffffff

def _load_pyc(name, filename, pyc_filename):
    try:
        fp = open(pyc_filename, "rb")
    except IOError:
        return None
    if fp.read(4) == imp.get_magic():
        mtime = struct.unpack('<I', fp.read(4))[0]
        ptl_mtime = _timestamp(filename)
        if ptl_mtime is not None and mtime == ptl_mtime:
            code = marshal.load(fp)
            return _exec_module_code(code, name, filename)
    return None

def _load_ptl(name, filename, file=None):
    if not file:
        try:
            file = open(filename, "rb")
        except IOError:
            return None
    path, ext = os.path.splitext(filename)
    pyc_filename = path + ".pyc"
    module = _load_pyc(name, filename, pyc_filename)
    if module is not None:
        return module
    try:
        output = open(pyc_filename, "wb")
    except IOError:
        output = None
    try:
        code = compile_template(file, filename, output)
    except:
        if output:
            output.close()
            os.unlink(pyc_filename)
        raise
    else:
        if output:
            output.close()
    return _exec_module_code(code, name, filename)


# Constant used to signal a PTL files
PTL_FILE = object()

class PTLHooks(ihooks.Hooks):

    def get_suffixes(self):
        # add our suffixes
        return [(PTL_EXT, 'r', PTL_FILE)] + imp.get_suffixes()

class PTLLoader(ihooks.ModuleLoader):

    def load_module(self, name, stuff):
        file, filename, info = stuff
        (suff, mode, type) = info

        # If it's a PTL file, load it specially.
        if type is PTL_FILE:
            return _load_ptl(name, filename, file)

        else:
            # Otherwise, use the default handler for loading
            return ihooks.ModuleLoader.load_module(self, name, stuff)

if sys.hexversion <= 0x20600b0:
    try:
        import cimport
    except ImportError:
        cimport = None
else:
    # cimport module doesn't handle relative imports
    cimport = None

class cModuleImporter(ihooks.ModuleImporter):
    def __init__(self, loader=None):
        self.loader = loader or ihooks.ModuleLoader()
        cimport.set_loader(self.find_import_module)

    def find_import_module(self, fullname, subname, path):
        stuff = self.loader.find_module(subname, path)
        if not stuff:
            return None
        return self.loader.load_module(fullname, stuff)

    def install(self):
        self.save_import_module = __builtin__.__import__
        self.save_reload = __builtin__.reload
        if not hasattr(__builtin__, 'unload'):
            __builtin__.unload = None
        self.save_unload = __builtin__.unload
        __builtin__.__import__ = cimport.import_module
        __builtin__.reload = cimport.reload_module
        __builtin__.unload = self.unload

_installed = False

def install():
    global _installed
    if not _installed:
        hooks = PTLHooks()
        loader = PTLLoader(hooks)
        if cimport is not None:
            importer = cModuleImporter(loader)
        else:
            importer = ihooks.ModuleImporter(loader)
        ihooks.install(importer)
        _installed = True


if __name__ == '__main__':
    install()
