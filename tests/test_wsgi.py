"""End-to-end tests driving a Publisher through its WSGI adapter.

They build a Publisher, obtain the WSGI application via
`quixote.get_wsgi_app()`, and call it with a synthetic environ, so no real
HTTP server is started.
"""

from collections.abc import Iterator

import pytest
from helpers import call

import quixote
from quixote.directory import Directory
from quixote.publish import Publisher
from quixote.wsgi import QWIP


class Root(Directory):
    _q_exports = ['', 'echo']

    def _q_index(self) -> str:
        return 'hello, world'

    def echo(self) -> str:
        return str(quixote.get_request().get_field('msg', ''))


@pytest.fixture
def app() -> Iterator[QWIP]:
    """Publisher wrapped as a WSGI application, cleaned up afterwards."""
    Publisher(Root())
    try:
        yield quixote.get_wsgi_app()
    finally:
        quixote.cleanup()


class TestWSGI:
    def test_index(self, app: QWIP) -> None:
        status, headers, body = call(app, '/')
        assert status == '200 OK'
        assert body == b'hello, world'
        assert headers['Content-Type'] == 'text/html; charset=utf-8'
        assert headers['Content-Length'] == str(len(b'hello, world'))

    def test_named_export_with_query(self, app: QWIP) -> None:
        status, _headers, body = call(app, '/echo', 'msg=hi')
        assert status == '200 OK'
        assert body == b'hi'

    def test_missing_export_is_404(self, app: QWIP) -> None:
        status, _headers, _body = call(app, '/nope')
        assert status.startswith('404')
