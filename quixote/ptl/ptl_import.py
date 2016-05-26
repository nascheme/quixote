"""Import hooks; when installed, these hooks allow importing .ptl files
as if they were Python modules.
"""

import sys
from importlib.machinery import FileFinder, PathFinder, SourceFileLoader
from .ptl_parse import parse

PTL_EXT = ".ptl"

class PTLFileLoader(SourceFileLoader):
    @staticmethod
    def source_to_code(data, path, *, _optimize=-1):
        node = parse(data, path)
        return compile(node, path, 'exec', dont_inherit=True,
                       optimize=_optimize)


class PTLPathFinder(PathFinder):
    path_importer_cache = {}

    @classmethod
    def _path_importer_cache(cls, path):
        try:
            finder = cls.path_importer_cache[path]
        except KeyError:
            finder = FileFinder(path, (PTLFileLoader, [PTL_EXT]))
            cls.path_importer_cache[path] = finder
        return finder

    @classmethod
    def invalidate_caches(cls):
        for finder in list(cls.path_importer_cache.values()):
            if hasattr(finder, 'invalidate_caches'):
                f = finder.invalidate_caches()


def install():
    if PTLPathFinder not in sys.meta_path:
        sys.meta_path.append(PTLPathFinder)


if __name__ == '__main__':
    install()
