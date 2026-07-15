"""Helpers for building synthetic requests and driving test publishers.

These are plain functions (not fixtures) so tests can call them with
explicit arguments; the shared `publisher` fixture lives in
quixote/conftest.py.
"""

import io
from collections.abc import Iterator
from contextlib import contextmanager
from typing import cast
from wsgiref.types import StartResponse
from wsgiref.util import setup_testing_defaults

from quixote.http_request import Environ, FieldValue, HTTPRequest
from quixote.publish import Publisher
from quixote.wsgi import QWIP


def make_environ(
    path: str = '/',
    method: str = 'GET',
    query: str = '',
    **extra: str,
) -> Environ:
    """Return a minimal CGI/WSGI environ for a synthetic request."""
    environ: dict[str, str] = {
        'SCRIPT_NAME': '',
        'PATH_INFO': path,
        'REQUEST_METHOD': method,
        'QUERY_STRING': query,
        'SERVER_NAME': 'example.com',
        'SERVER_PORT': '80',
        'SERVER_PROTOCOL': 'HTTP/1.1',
        'REMOTE_ADDR': '127.0.0.1',
    }
    environ.update(extra)
    return environ


def make_request(
    form: dict[str, FieldValue] | None = None,
    method: str = 'POST',
    **environ_kw: str,
) -> HTTPRequest:
    """Return an HTTPRequest with `form` already populated.

    No publisher is needed; pass the result to APIs that accept an
    explicit request, e.g. `widget.parse(request=...)`.
    """
    request = HTTPRequest(None, make_environ(method=method, **environ_kw))
    if form:
        request.form.update(form)
    return request


@contextmanager
def request_context(
    publisher: Publisher,
    request: HTTPRequest | None = None,
    **environ_kw: str,
) -> Iterator[HTTPRequest]:
    """Make `request` the active request for the duration of the block.

    Uses the publisher's private request slot directly, so code under
    test can call quixote.get_request()/get_response() without going
    through the full WSGI pipeline.
    """
    if request is None:
        request = HTTPRequest(None, make_environ(**environ_kw))
    publisher._set_request(request)
    try:
        yield request
    finally:
        publisher._clear_request()


def call(
    app: QWIP, path: str, query: str = '', method: str = 'GET'
) -> tuple[str, dict[str, str], bytes]:
    """Drive `app` for one request; return (status, headers, body)."""
    env = {
        'PATH_INFO': path,
        'SCRIPT_NAME': '',
        'QUERY_STRING': query,
        'REQUEST_METHOD': method,
        'wsgi.input': io.BytesIO(b''),
    }
    setup_testing_defaults(env)
    captured: dict[str, object] = {}

    def start_response(status: str, headers: list[tuple[str, str]]) -> None:
        captured['status'] = status
        captured['headers'] = dict(headers)

    body = b''.join(app(env, cast(StartResponse, start_response)))
    return captured['status'], captured['headers'], body  # type: ignore
