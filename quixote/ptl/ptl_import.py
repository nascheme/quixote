"""Import hooks; when installed, these hooks allow importing .ptl files
as if they were Python modules.
"""

from importlib.machinery import FileFinder, PathFinder, SourceFileLoader
import re
import sys
from .ptl_parse import parse


PTL_EXT = ".ptl"


# Must appear within first 2 kB of start of file.  E.g. # ptl: enable
_HAS_PTL_PRAGMA = re.compile(
    rb'^[ \t\f]*#[ \t]*ptl:[ \t]*enable\b', re.M
).search


def _is_ptl(buf, path):
    if path.endswith(PTL_EXT):
        return True
    if _HAS_PTL_PRAGMA(buf[:2048]):
        return True
    return False


class PTLFileLoader(SourceFileLoader):
    def source_to_code(self, data, path, *, _optimize=-1):
        ptl = _is_ptl(data, path)
        if not ptl:
            return super().source_to_code(data, path, _optimize=_optimize)
        else:
            node = parse(data, path)
            return compile(
                node, path, 'exec', dont_inherit=True, optimize=_optimize
            )


class PTLPathFinder(PathFinder):

    # allow PTL to be imported from .py files
    _ENABLE_PY_EXTENSION = False

    path_importer_cache = {}

    @classmethod
    def _path_importer_cache(cls, path):
        try:
            finder = cls.path_importer_cache[path]
        except KeyError:
            if cls._ENABLE_PY_EXTENSION:
                ext = [PTL_EXT, ".py"]
            else:
                ext = [PTL_EXT]
            finder = FileFinder(path, (PTLFileLoader, ext))
            cls.path_importer_cache[path] = finder
        return finder

    @classmethod
    def invalidate_caches(cls):
        for finder in list(cls.path_importer_cache.values()):
            if hasattr(finder, 'invalidate_caches'):
                finder.invalidate_caches()


def install():
    if PTLPathFinder not in sys.meta_path:
        sys.meta_path.append(PTLPathFinder)


def install_for_py():
    if (
        PTLPathFinder not in sys.meta_path
        or not PTLPathFinder._ENABLE_PY_EXTENSION
    ):
        PTLPathFinder._ENABLE_PY_EXTENSION = True
        if PTLPathFinder in sys.meta_path:
            sys.meta_path.remove(PTLPathFinder)
        sys.meta_path.insert(0, PTLPathFinder)


if __name__ == '__main__':
    install()
