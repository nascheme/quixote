"""Tests for the Publisher singleton and the quixote.get_* helpers."""

from collections.abc import Iterator
from typing import cast

import pytest
from helpers import call, request_context

import quixote
from quixote.config import Config
from quixote.directory import Directory
from quixote.publish import Publisher
from quixote.wsgi import QWIP


class Root(Directory):
    _q_exports = ['']

    def _q_index(self) -> str:
        return 'index'


class TestPublisherLifecycle:
    def test_second_publisher_raises_runtime_error(self) -> None:
        Publisher(Root())
        try:
            with pytest.raises(RuntimeError):
                Publisher(Root())
        finally:
            quixote.cleanup()

    def test_cleanup_allows_a_new_publisher(self) -> None:
        Publisher(Root())
        quixote.cleanup()
        try:
            second = Publisher(Root())
            assert quixote.get_publisher() is second
        finally:
            quixote.cleanup()

    def test_non_callable_q_traverse_raises_type_error(self) -> None:
        class BadRoot:
            _q_traverse = 'not callable'

        try:
            with pytest.raises(TypeError):
                Publisher(cast(Directory, BadRoot()))
        finally:
            quixote.cleanup()

    def test_config_object_and_config_kwargs_conflict(self) -> None:
        try:
            with pytest.raises(ValueError):
                Publisher(Root(), config=Config(), display_exceptions=True)
        finally:
            quixote.cleanup()

    def test_get_publisher_without_publisher_raises(self) -> None:
        with pytest.raises(RuntimeError):
            quixote.get_publisher()

    def test_get_request_between_requests_raises(
        self, publisher: Publisher
    ) -> None:
        with pytest.raises(RuntimeError):
            quixote.get_request()

    def test_get_request_returns_the_active_request(
        self, publisher: Publisher
    ) -> None:
        with request_context(publisher) as request:
            assert quixote.get_request() is request


class TestRequestHelpers:
    def test_get_response_is_the_active_requests_response(
        self, publisher: Publisher
    ) -> None:
        with request_context(publisher) as request:
            assert quixote.get_response() is request.response

    def test_get_field_returns_all_values_get_param_the_last(
        self, publisher: Publisher
    ) -> None:
        with request_context(publisher, query='a=1&a=2&b=x') as request:
            request.process_inputs()
            assert quixote.get_field('a') == ['1', '2']
            assert quixote.get_param('a') == '2'
            assert quixote.get_field('b') == 'x'
            assert quixote.get_param('b') == 'x'

    def test_field_helpers_return_default_when_missing(
        self, publisher: Publisher
    ) -> None:
        with request_context(publisher) as request:
            request.process_inputs()
            assert quixote.get_field('nope', 'dflt') == 'dflt'
            assert quixote.get_param('nope', 'dflt') == 'dflt'

    def test_get_path_drops_trailing_components(
        self, publisher: Publisher
    ) -> None:
        with request_context(publisher, path='/foo/bar'):
            assert quixote.get_path() == '/foo/bar'
            assert quixote.get_path(1) == '/foo'

    def test_get_cookie_reads_the_cookie_header(
        self, publisher: Publisher
    ) -> None:
        with request_context(publisher, HTTP_COOKIE='sid=abc'):
            assert quixote.get_cookie('sid') == 'abc'
            assert quixote.get_cookie('nope', 'dflt') == 'dflt'
            assert quixote.get_cookie(None, 'dflt') == 'dflt'


class TestRedirect:
    def test_redirect_resolves_relative_location(
        self, publisher: Publisher
    ) -> None:
        with request_context(publisher, path='/foo/bar'):
            body = quixote.redirect('baz')
            response = quixote.get_response()
        assert response.get_status_code() == 302
        assert response.get_header('location') == 'http://example.com/foo/baz'
        assert 'http://example.com/foo/baz' in body

    def test_permanent_redirect_is_301(self, publisher: Publisher) -> None:
        with request_context(publisher, path='/foo/bar'):
            quixote.redirect('http://elsewhere.org/', permanent=True)
            response = quixote.get_response()
        assert response.get_status_code() == 301
        assert response.get_header('location') == 'http://elsewhere.org/'


class TestSessionHelpers:
    def test_null_session_manager_yields_no_session_or_user(
        self, publisher: Publisher
    ) -> None:
        with request_context(publisher):
            assert quixote.get_session() is None
            assert quixote.get_user() is None

    def test_get_session_manager_returns_the_publishers_manager(
        self, publisher: Publisher
    ) -> None:
        manager = quixote.get_session_manager()
        assert manager is publisher.session_manager


@pytest.fixture
def get_only_app() -> Iterator[QWIP]:
    Publisher(Root(), allowed_methods=['GET'])
    try:
        yield quixote.get_wsgi_app()
    finally:
        quixote.cleanup()


class TestAllowedMethods:
    def test_disallowed_method_gets_405_with_allow_header(
        self, get_only_app: QWIP
    ) -> None:
        status, headers, _body = call(get_only_app, '/', method='POST')
        assert status.startswith('405')
        assert headers['Allow'] == 'GET'

    def test_allowed_method_is_published(self, get_only_app: QWIP) -> None:
        status, _headers, body = call(get_only_app, '/')
        assert status == '200 OK'
        assert body == b'index'
