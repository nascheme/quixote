"""Tests for the PublishError hierarchy and error-page rendering."""

from collections.abc import Iterator

import pytest
from helpers import call, request_context

import quixote
from quixote.directory import Directory
from quixote.errors import (
    AccessError,
    MethodNotAllowedError,
    PublishError,
    QueryError,
    RequestError,
    TraversalError,
    format_page,
    format_publish_error,
)
from quixote.html import htmltext
from quixote.publish import Publisher
from quixote.wsgi import QWIP


class TestStatusMapping:
    @pytest.mark.parametrize(
        'exc,status_code,title',
        [
            (PublishError(), 400, 'Publishing error'),
            (TraversalError(path='/x'), 404, 'Page not found'),
            (RequestError(), 400, 'Invalid request'),
            (QueryError(), 400, 'Invalid query'),
            (AccessError(), 403, 'Access denied'),
            (MethodNotAllowedError(['GET']), 405, 'Method not allowed'),
        ],
    )
    def test_each_error_maps_to_its_http_status(
        self, exc: PublishError, status_code: int, title: str
    ) -> None:
        assert exc.status_code == status_code
        assert exc.title == title


class TestStringForm:
    def test_str_prefers_the_private_message(self) -> None:
        exc = PublishError(public_msg='public', private_msg='private')
        assert str(exc) == 'private'

    def test_str_falls_back_to_the_public_message(self) -> None:
        assert str(PublishError(public_msg='public')) == 'public'

    def test_str_without_messages_is_a_placeholder(self) -> None:
        assert str(PublishError()) == '???'


class TestFormat:
    def test_format_includes_title_and_both_messages(self) -> None:
        exc = PublishError(public_msg='pub msg', private_msg='priv msg')
        text = str(exc.format())
        assert 'Publishing error' in text
        assert 'pub msg' in text
        assert 'priv msg' in text

    def test_format_escapes_markup_in_the_public_message(self) -> None:
        exc = PublishError(public_msg='<b>bold</b>')
        assert '&lt;b&gt;bold&lt;/b&gt;' in str(exc.format())

    def test_traversal_error_format_escapes_the_path(self) -> None:
        exc = TraversalError(path='/x/<y>')
        assert '/x/&lt;y&gt;' in str(exc.format())


class TestPageRendering:
    def test_format_page_escapes_an_untrusted_title(self) -> None:
        text = str(format_page('a <b> title', htmltext('<p>body</p>')))
        assert 'a &lt;b&gt; title' in text

    def test_format_page_passes_htmltext_body_through(self) -> None:
        text = str(format_page('title', htmltext('<p>body</p>')))
        assert '<p>body</p>' in text

    def test_format_publish_error_combines_the_error_parts(self) -> None:
        exc = QueryError(public_msg='bad data')
        text = str(format_publish_error(exc))
        assert 'Error: Invalid query' in text
        assert QueryError.description in text
        assert 'bad data' in text


class TestRequestContextErrors:
    def test_bare_traversal_error_records_the_request_path(
        self, publisher: Publisher
    ) -> None:
        with request_context(publisher, path='/a/b'):
            exc = TraversalError()
        assert exc.path == '/a/b'

    def test_method_not_allowed_format_sets_the_allow_header(
        self, publisher: Publisher
    ) -> None:
        with request_context(publisher):
            text = str(MethodNotAllowedError(['GET', 'POST']).format())
            response = quixote.get_response()
        assert text == 'Allowed methods are: GET, POST'
        assert response.get_header('allow') == 'GET, POST'


class Root(Directory):
    _q_exports = ['bad']

    def bad(self) -> str:
        raise QueryError(public_msg='bad id', private_msg='secret detail')


@pytest.fixture
def app() -> Iterator[QWIP]:
    Publisher(Root())
    try:
        yield quixote.get_wsgi_app()
    finally:
        quixote.cleanup()


class TestPublishErrorResponse:
    def test_publish_error_aborts_with_its_status_and_public_msg(
        self, app: QWIP
    ) -> None:
        status, _headers, body = call(app, '/bad')
        assert status.startswith('400')
        assert b'bad id' in body

    def test_private_msg_is_suppressed_by_default(self, app: QWIP) -> None:
        _status, _headers, body = call(app, '/bad')
        assert b'secret detail' not in body
