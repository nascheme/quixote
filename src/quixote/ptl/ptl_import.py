"""Import hooks; when installed, these hooks allow importing .ptl files
as if they were Python modules.
"""

from __future__ import annotations

import os
import sys
from importlib.machinery import FileFinder, PathFinder, SourceFileLoader
from types import CodeType
from typing import Any

from .ptl_parse import parse

PTL_EXT = ".ptl"


class PTLFileLoader(SourceFileLoader):
    @staticmethod
    def source_to_code(  # pyrefly: ignore[bad-override]  # TODO: Preserve legacy staticmethod API.
        data: Any, path: Any = '<string>', *, _optimize: int = -1
    ) -> CodeType:
        path_str = os.fsdecode(path)
        if isinstance(data, str | bytes):
            node = parse(data, path_str)
        else:
            node = data
        return compile(
            node, path_str, 'exec', dont_inherit=True, optimize=_optimize
        )


class PTLPathFinder(PathFinder):
    path_importer_cache: dict[str, FileFinder] = {}

    @classmethod
    def _path_importer_cache(cls, path: str) -> FileFinder:
        try:
            finder = cls.path_importer_cache[path]
        except KeyError:
            finder = FileFinder(path, (PTLFileLoader, [PTL_EXT]))
            cls.path_importer_cache[path] = finder
        return finder

    @classmethod
    def invalidate_caches(cls: type[PTLPathFinder]) -> None:
        for finder in list(cls.path_importer_cache.values()):
            if hasattr(finder, 'invalidate_caches'):
                finder.invalidate_caches()


def install() -> None:
    if PTLPathFinder not in sys.meta_path:
        sys.meta_path.append(PTLPathFinder)


if __name__ == '__main__':
    install()
