#!/usr/bin/env python
"""Compile a PTL template.
"""

import sys
import os
import struct
import importlib.util
import py_compile
from quixote.ptl.ptl_import import PTL_EXT, PTLFileLoader


def ptl_compile(file, cfile, dfile=None, doraise=False, optimize=-1):
    """Byte-compile one PTL source file to Python bytecode.

    :param file: The source file name.
    :param cfile: The target byte compiled file name.
    :param dfile: Purported file name, i.e. the file name that shows up in
        error messages.  Defaults to the source file name.
    :param doraise: Flag indicating whether or not an exception should be
        raised when a compile error is found.  If an exception occurs and this
        flag is set to False, a string indicating the nature of the exception
        will be printed, and the function will return to the caller. If an
        exception occurs and this flag is set to True, a PyCompileError
        exception will be raised.
    :param optimize: The optimization level for the compiler.  Valid values
        are -1, 0, 1 and 2.  A value of -1 means to use the optimization
        level of the current interpreter, as given by -O command line options.

    :return: Path to the resulting byte compiled file.

    Do note that FileExistsError is raised if cfile ends up pointing at a
    non-regular file or symlink. Because the compilation uses a file renaming,
    the resulting file would be regular and thus not the same type of file as
    it was previously.
    """
    # derived from py_compile.compile
    if os.path.islink(cfile):
        msg = (
            '{} is a symlink and will be changed into a regular file if '
            'import writes a byte-compiled file to it'
        )
        raise FileExistsError(msg.format(cfile))
    elif os.path.exists(cfile) and not os.path.isfile(cfile):
        msg = (
            '{} is a non-regular file and will be changed into a regular '
            'one if import writes a byte-compiled file to it'
        )
        raise FileExistsError(msg.format(cfile))
    loader = PTLFileLoader('<ptl_compile>', file)
    source_bytes = loader.get_data(file)
    try:
        code = loader.source_to_code(
            source_bytes, dfile or file, _optimize=optimize
        )
    except Exception as err:
        py_exc = py_compile.PyCompileError(err.__class__, err, dfile or file)
        if doraise:
            raise py_exc
        else:
            sys.stderr.write(py_exc.msg + '\n')
            return
    try:
        dirname = os.path.dirname(cfile)
        if dirname:
            os.makedirs(dirname)
    except FileExistsError:
        pass
    source_stats = loader.path_stats(file)
    bytecode = _code_to_bytecode(
        code, source_stats['mtime'], source_stats['size']
    )
    mode = importlib._bootstrap_external._calc_mode(file)
    importlib._bootstrap_external._write_atomic(cfile, bytecode, mode)
    return cfile


# derived from compileall.py
def _walk_dir(dir, ddir=None, maxlevels=10, quiet=0):
    if not quiet:
        print('Listing {!r}...'.format(dir))
    try:
        names = os.listdir(dir)
    except OSError:
        if quiet < 2:
            print("Can't list {!r}".format(dir))
        names = []
    names.sort()
    for name in names:
        if name == '__pycache__':
            continue
        fullname = os.path.join(dir, name)
        if ddir is not None:
            dfile = os.path.join(ddir, name)
        else:
            dfile = None
        if not os.path.isdir(fullname):
            yield fullname
        elif (
            maxlevels > 0
            and name != os.curdir
            and name != os.pardir
            and os.path.isdir(fullname)
            and not os.path.islink(fullname)
        ):
            yield from _walk_dir(
                fullname, ddir=dfile, maxlevels=maxlevels - 1, quiet=quiet
            )


# derived from compileall.py
def compile_dir(
    dir,
    maxlevels=10,
    ddir=None,
    force=False,
    rx=None,
    quiet=0,
    legacy=False,
    optimize=-1,
    workers=1,
):
    """Byte-compile all modules in the given directory tree.

    Arguments (only dir is required):

    dir:       the directory to byte-compile
    maxlevels: maximum recursion level (default 10)
    ddir:      the directory that will be prepended to the path to the
               file as it is compiled into each byte-code file.
    force:     if True, force compilation, even if timestamps are up-to-date
    quiet:     full output with False or 0, errors only with 1,
               no output with 2
    legacy:    if True, produce legacy pyc paths instead of PEP 3147 paths
    optimize:  optimization level or -1 for level of the interpreter
    workers:   maximum number of parallel workers
    """
    files = _walk_dir(dir, quiet=quiet, maxlevels=maxlevels, ddir=ddir)
    success = 1
    for file in files:
        if not compile_file(file, ddir, force, rx, quiet, legacy, optimize):
            success = 0
    return success


# derived from compileall.py
def compile_file(
    fullname,
    ddir=None,
    force=False,
    rx=None,
    quiet=0,
    legacy=False,
    optimize=-1,
):
    """Byte-compile one file.

    Arguments (only fullname is required):

    fullname:  the file to byte-compile
    ddir:      if given, the directory name compiled in to the
               byte-code file.
    force:     if True, force compilation, even if timestamps are up-to-date
    quiet:     full output with False or 0, errors only with 1,
               no output with 2
    legacy:    if True, produce legacy pyc paths instead of PEP 3147 paths
    optimize:  optimization level or -1 for level of the interpreter
    """
    success = 1
    name = os.path.basename(fullname)
    if ddir is not None:
        dfile = os.path.join(ddir, name)
    else:
        dfile = None
    if rx is not None:
        mo = rx.search(fullname)
        if mo:
            return success
    if os.path.isfile(fullname):
        if legacy:
            cfile = fullname[: -len(PTL_EXT)] + '.pyc'
        else:
            if optimize >= 0:
                opt = optimize if optimize >= 1 else ''
                cfile = importlib.util.cache_from_source(
                    fullname, optimization=opt
                )
            else:
                cfile = importlib.util.cache_from_source(fullname)
        tail = name[-4:]
        if tail == PTL_EXT:
            if not force:
                try:
                    mtime = int(os.stat(fullname).st_mtime)
                    expect = struct.pack(
                        '<4sl', importlib.util.MAGIC_NUMBER, mtime
                    )
                    with open(cfile, 'rb') as chandle:
                        actual = chandle.read(8)
                    if expect == actual:
                        return success
                except OSError:
                    pass
            if not quiet:
                print('Compiling {!r}...'.format(fullname))
            try:
                ok = ptl_compile(
                    fullname, cfile, dfile, True, optimize=optimize
                )
            except py_compile.PyCompileError as err:
                success = 0
                if quiet >= 2:
                    return success
                elif quiet:
                    print('*** Error compiling {!r}...'.format(fullname))
                else:
                    print('*** ', end='')
                # escape non-printable characters in msg
                msg = err.msg.encode(
                    sys.stdout.encoding, errors='backslashreplace'
                )
                msg = msg.decode(sys.stdout.encoding)
                print(msg)
            except (SyntaxError, UnicodeError, OSError) as e:
                success = 0
                if quiet >= 2:
                    return success
                elif quiet:
                    print('*** Error compiling {!r}...'.format(fullname))
                else:
                    print('*** ', end='')
                print(e.__class__.__name__ + ':', e)
            else:
                if ok == 0:
                    success = 0
    return success


# derived from compileall.py
def compile_path(
    skip_curdir=1,
    maxlevels=0,
    force=False,
    quiet=0,
    legacy=False,
    optimize=-1,
):
    """Byte-compile all module on sys.path.

    Arguments (all optional):

    skip_curdir: if true, skip current directory (default True)
    maxlevels:   max recursion level (default 0)
    force: as for compile_dir() (default False)
    quiet: as for compile_dir() (default 0)
    legacy: as for compile_dir() (default False)
    optimize: as for compile_dir() (default -1)
    """
    success = 1
    for dir in sys.path:
        if (not dir or dir == os.curdir) and skip_curdir:
            if quiet < 2:
                print('Skipping current directory')
        else:
            success = success and compile_dir(
                dir,
                maxlevels,
                None,
                force,
                quiet=quiet,
                legacy=legacy,
                optimize=optimize,
            )
    return success


def compile_package(paths, force=0, verbose=0):
    """Compile all PTL files in a package.  'path' should be a list
    of directory names containing the files of the package (i.e. __path__).
    """
    for path in paths:
        compile_dir(path, quiet=0 if verbose else 1, force=force, legacy=1)


def main():
    """Script main program."""
    import argparse

    parser = argparse.ArgumentParser(
        description='Utilities to support installing Python libraries.'
    )
    parser.add_argument(
        '-l',
        action='store_const',
        const=0,
        default=10,
        dest='maxlevels',
        help="don't recurse into subdirectories",
    )
    parser.add_argument(
        '-r',
        type=int,
        dest='recursion',
        help=(
            'control the maximum recursion level. '
            'if `-l` and `-r` options are specified, '
            'then `-r` takes precedence.'
        ),
    )
    parser.add_argument(
        '-f',
        action='store_true',
        dest='force',
        help='force rebuild even if timestamps are up to date',
    )
    parser.add_argument(
        '-q',
        action='count',
        dest='quiet',
        default=0,
        help='output only error messages; -qq will suppress '
        'the error messages as well.',
    )
    parser.add_argument(
        '-b',
        action='store_true',
        dest='legacy',
        help='use legacy (pre-PEP3147) compiled file locations',
    )
    parser.add_argument(
        '-d',
        metavar='DESTDIR',
        dest='ddir',
        default=None,
        help=(
            'directory to prepend to file paths for use in '
            'compile-time tracebacks and in runtime '
            'tracebacks in cases where the source file is '
            'unavailable'
        ),
    )
    parser.add_argument(
        '-x',
        metavar='REGEXP',
        dest='rx',
        default=None,
        help=(
            'skip files matching the regular expression; '
            'the regexp is searched for in the full path '
            'of each file considered for compilation'
        ),
    )
    parser.add_argument(
        '-i',
        metavar='FILE',
        dest='flist',
        help=(
            'add all the files and directories listed in '
            'FILE to the list considered for compilation; '
            'if "-", names are read from stdin'
        ),
    )
    parser.add_argument(
        'compile_dest',
        metavar='FILE|DIR',
        nargs='*',
        help=(
            'zero or more file and directory names '
            'to compile; if no arguments given, defaults '
            'to the equivalent of -l sys.path'
        ),
    )
    parser.add_argument(
        '-j',
        '--workers',
        default=1,
        type=int,
        help='Run compileall concurrently',
    )

    args = parser.parse_args()
    compile_dests = args.compile_dest

    if args.ddir and (
        len(compile_dests) != 1 or not os.path.isdir(compile_dests[0])
    ):
        parser.exit('-d destdir requires exactly one directory argument')
    if args.rx:
        import re

        args.rx = re.compile(args.rx)

    if args.recursion is not None:
        maxlevels = args.recursion
    else:
        maxlevels = args.maxlevels

    # if flist is provided then load it
    if args.flist:
        try:
            with (sys.stdin if args.flist == '-' else open(args.flist)) as f:
                for line in f:
                    compile_dests.append(line.strip())
        except OSError:
            if args.quiet < 2:
                print("Error reading file list {}".format(args.flist))
            return False

    if args.workers is not None:
        args.workers = args.workers or None

    success = True
    try:
        if compile_dests:
            for dest in compile_dests:
                if os.path.isfile(dest):
                    if not compile_file(
                        dest,
                        args.ddir,
                        args.force,
                        args.rx,
                        args.quiet,
                        args.legacy,
                    ):
                        success = False
                else:
                    if not compile_dir(
                        dest,
                        maxlevels,
                        args.ddir,
                        args.force,
                        args.rx,
                        args.quiet,
                        args.legacy,
                        workers=args.workers,
                    ):
                        success = False
            return success
        else:
            return compile_path(
                legacy=args.legacy, force=args.force, quiet=args.quiet
            )
    except KeyboardInterrupt:
        if args.quiet < 2:
            print("\n[interrupted]")
        return False
    return True


if hasattr(importlib._bootstrap_external, '_code_to_bytecode'):
    _code_to_bytecode = importlib._bootstrap_external._code_to_bytecode
else:
    # renamed in Python 3.7
    _code_to_bytecode = importlib._bootstrap_external._code_to_timestamp_pyc


def compile_template(input, filename, output=None):
    """(input, filename) -> code

    Compile an open file.  The code object is returned.
    """
    source_bytes = input.read()
    loader = PTLFileLoader('<ptl_compile>', filename)
    code = loader.source_to_code(source_bytes, filename)
    if output is not None:
        # The 'output' parameter is for backwards compatibility with old
        # versions of Quixote.  New code should not supply it.
        bytecode = _code_to_bytecode(code, 0, 0)
        output.write(bytecode)
    return code


if __name__ == '__main__':
    exit_status = int(not main())
    sys.exit(exit_status)
