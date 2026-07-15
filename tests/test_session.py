"""Tests for Session, form/CSRF tokens, and SessionManager.

Constructing a Session reads the current request (remote address), so
these tests run inside a publisher request context.  The cookie
lifecycle tests use a publisher configured with a real SessionManager
instead of the default NullSessionManager.
"""

from collections.abc import Iterator

import pytest
from helpers import request_context

import quixote
from quixote.directory import Directory
from quixote.publish import Publisher
from quixote.session import (
    CSRF_TOKEN_NAME,
    NullSessionManager,
    Session,
    SessionManager,
)


class Root(Directory):
    _q_exports = ['']

    def _q_index(self) -> str:
        return 'index'


@pytest.fixture
def session_publisher() -> Iterator[Publisher]:
    """A publisher whose sessions are kept by a real SessionManager."""
    pub = Publisher(Root(), session_manager=SessionManager())
    try:
        yield pub
    finally:
        quixote.cleanup()


class TestSession:
    def test_a_new_session_is_empty(self, publisher: Publisher) -> None:
        with request_context(publisher):
            session = Session('abc')
        assert session.id == 'abc'
        assert session.get_user() is None
        assert session.get_remote_address() == '127.0.0.1'
        assert session.has_info() is False

    def test_setting_a_user_gives_the_session_info(
        self, publisher: Publisher
    ) -> None:
        with request_context(publisher):
            session = Session(None)
        session.set_user('alice')
        assert session.get_user() == 'alice'
        assert session.has_info() is True

    def test_start_request_exports_the_user_to_the_environ(
        self, publisher: Publisher
    ) -> None:
        with request_context(publisher) as request:
            session = Session(None)
            session.set_user('alice')
            session.start_request()
            assert request.get_environ('REMOTE_USER') == 'alice'


class TestFormTokens:
    def test_created_tokens_are_outstanding_until_removed(
        self, publisher: Publisher
    ) -> None:
        with request_context(publisher):
            session = Session(None)
        token = session.create_form_token()
        assert session.has_form_token(token) is True
        session.remove_form_token(token)
        assert session.has_form_token(token) is False

    def test_the_oldest_token_is_dropped_beyond_the_maximum(
        self, publisher: Publisher
    ) -> None:
        with request_context(publisher):
            session = Session(None)
        first = session.create_form_token()
        last = first
        for _i in range(Session.MAX_FORM_TOKENS):
            last = session.create_form_token()
        assert session.has_form_token(first) is False
        assert session.has_form_token(last) is True


class TestCsrfTokens:
    def test_the_csrf_token_is_stable_within_a_session(
        self, publisher: Publisher
    ) -> None:
        with request_context(publisher):
            session = Session(None)
        assert session.get_csrf_token() == session.get_csrf_token()

    def test_a_get_request_never_validates(
        self, publisher: Publisher
    ) -> None:
        with request_context(publisher) as request:
            session = Session(None)
            request.form[CSRF_TOKEN_NAME] = session.get_csrf_token()
            assert session.valid_csrf_token() is False

    def test_a_post_with_the_matching_token_validates(
        self, publisher: Publisher
    ) -> None:
        with request_context(publisher, method='POST') as request:
            session = Session(None)
            request.form[CSRF_TOKEN_NAME] = session.get_csrf_token()
            assert session.valid_csrf_token() is True

    def test_a_post_with_a_wrong_token_does_not_validate(
        self, publisher: Publisher
    ) -> None:
        with request_context(publisher, method='POST') as request:
            session = Session(None)
            session.get_csrf_token()
            request.form[CSRF_TOKEN_NAME] = 'wrong'
            assert session.valid_csrf_token() is False


class TestSessionManagerMapping:
    def test_stored_sessions_are_found_again(
        self, publisher: Publisher
    ) -> None:
        manager = SessionManager()
        with request_context(publisher):
            session = Session('sid1')
        manager['sid1'] = session
        assert 'sid1' in manager
        assert manager.has_session('sid1') is True
        assert manager['sid1'] is session
        assert manager.get('sid1') is session
        assert manager.keys() == ['sid1']
        assert manager.values() == [session]
        assert manager.items() == [('sid1', session)]

    def test_missing_sessions_give_the_default_or_raise(
        self, publisher: Publisher
    ) -> None:
        manager = SessionManager()
        assert manager.get('nope', 'dflt') == 'dflt'
        assert 'nope' not in manager
        with pytest.raises(KeyError):
            del manager['nope']

    def test_deleted_sessions_are_gone(self, publisher: Publisher) -> None:
        manager = SessionManager()
        with request_context(publisher):
            session = Session('sid1')
        manager['sid1'] = session
        del manager['sid1']
        assert 'sid1' not in manager


class TestSessionLifecycle:
    def test_start_request_attaches_a_session_to_the_request(
        self, session_publisher: Publisher
    ) -> None:
        manager = session_publisher.session_manager
        with request_context(session_publisher) as request:
            manager.start_request()
            assert isinstance(request.session, Session)
            assert request.session.id is None

    def test_a_session_with_info_is_stored_and_sets_the_cookie(
        self, session_publisher: Publisher
    ) -> None:
        manager = session_publisher.session_manager
        with request_context(session_publisher) as request:
            session = Session(None)
            session.set_user('alice')
            manager.maintain_session(session)
            assert session.id is not None
            assert session.id in manager
            cookie = request.response.cookies['QX_session']
            assert cookie['value'] == session.id

    def test_a_session_that_lost_its_info_is_forgotten(
        self, session_publisher: Publisher
    ) -> None:
        manager = session_publisher.session_manager
        with request_context(session_publisher) as request:
            session = Session(None)
            session.set_user('alice')
            manager.maintain_session(session)
            session.set_user(None)
            manager.maintain_session(session)
            assert session.id not in manager
            cookie = request.response.cookies['QX_session']
            assert cookie['value'] == ''
            assert cookie['max_age'] == 0

    def test_expire_session_forgets_the_current_session(
        self, session_publisher: Publisher
    ) -> None:
        manager = session_publisher.session_manager
        with request_context(session_publisher) as request:
            session = Session(None)
            session.set_user('alice')
            manager.maintain_session(session)
            request.session = session
            manager.expire_session()
            assert session.id not in manager
            assert request.session is None


class TestNullSessionManager:
    def test_it_stores_nothing(self) -> None:
        manager = NullSessionManager()
        assert manager.get('anything', 'dflt') == 'dflt'
        assert list(manager) == []
