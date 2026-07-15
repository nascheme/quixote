"""Shared pytest fixtures for the Quixote test suite."""

from collections.abc import Iterator

import pytest

import quixote
from quixote.directory import Directory
from quixote.publish import Publisher


class SimpleRoot(Directory):
    _q_exports = ['']

    def _q_index(self) -> str:
        return 'index'


@pytest.fixture
def publisher() -> Iterator[Publisher]:
    """A Publisher with a minimal root, cleaned up afterwards.

    Only one Publisher may exist per process; tests needing a custom root
    or config must construct their own Publisher (without this fixture)
    and call quixote.cleanup() themselves.
    """
    pub = Publisher(SimpleRoot())
    try:
        yield pub
    finally:
        quixote.cleanup()
