"""Tests for HTTPRequest.guess_browser_version()."""

import pytest

from quixote.http_request import HTTPRequest


def guess(user_agent: str | None) -> tuple[str | None, str | None]:
    env = {}
    if user_agent is not None:
        env['HTTP_USER_AGENT'] = user_agent
    return HTTPRequest(None, env).guess_browser_version()


class TestGuessBrowserVersion:
    @pytest.mark.parametrize(
        'user_agent, expected',
        [
            # Plain product string outside any comment.
            (
                'Mozilla/5.0 (X11; Linux x86_64; rv:78.0) '
                'Gecko/20100101 Firefox/78.0',
                ('Mozilla', '5.0'),
            ),
            ('Opera/9.80 (Windows NT 6.1) Presto/2.12', ('Opera', '9.80')),
            # MSIE masquerading as Mozilla via a "compatible" comment.
            ('Mozilla/5.0 (compatible; MSIE 5.5)', ('MSIE', '5.5')),
            (
                'Mozilla/4.0 (compatible; MSIE 6.0; Windows NT 5.1)',
                ('MSIE', '6.0'),
            ),
            # Konqueror does the same, with a slash-delimited version.
            (
                'Mozilla/5.0 (compatible; Konqueror/3.5; Linux) '
                'KHTML/3.5.5 (like Gecko)',
                ('Konqueror', '3.5'),
            ),
        ],
    )
    def test_parse(
        self,
        user_agent: str,
        expected: tuple[str | None, str | None],
    ) -> None:
        assert guess(user_agent) == expected

    def test_missing_header(self) -> None:
        assert guess(None) == (None, None)
