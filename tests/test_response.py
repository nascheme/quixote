import gzip
from collections.abc import Iterable
from typing import cast

import pytest

from quixote.http_response import HTTPResponse, Stream


def generated_headers(response: HTTPResponse) -> dict[str, str]:
    """Return the generated headers as a lower-cased-name dict."""
    return {
        name.lower(): value for name, value in response.generate_headers()
    }


class ClosingStream(Stream):
    def __init__(
        self, iterable: Iterable[str | bytes], length: int | None = None
    ) -> None:
        super().__init__(iterable, length)
        self.closed = False

    def close(self) -> None:
        self.closed = True


class TestHTTPResponse:
    def test_generate_headers_sets_content_length(self) -> None:
        response = HTTPResponse(body='hé')

        headers = {
            name.lower(): value for name, value in response.generate_headers()
        }

        assert headers['content-type'] == 'text/html; charset=utf-8'
        assert headers['content-length'] == str(len('hé'.encode('utf-8')))

    def test_stream_uses_chunked_transfer(self) -> None:
        stream = ClosingStream([b'abc', b'd'])
        response = HTTPResponse(body=stream)
        response.enable_transfer_chunked()

        headers = {
            name.lower(): value for name, value in response.generate_headers()
        }
        body = list(response.generate_body_chunks())

        assert headers['transfer-encoding'] == 'chunked'
        assert body == [b'3\r\nabc\r\n', b'1\r\nd\r\n', b'0\r\n\r\n']
        assert stream.closed

    def test_set_cookie_generates_cookie_headers(self) -> None:
        response = HTTPResponse()
        response.set_cookie(
            'session',
            'abc',
            path='/',
            secure=True,
            httponly=1,
        )

        headers = response.generate_headers()

        assert (
            'Set-Cookie',
            'session="abc"; path=/; secure; httponly',
        ) in headers


class TestSetStatus:
    def test_non_integer_status_is_rejected(self) -> None:
        with pytest.raises(TypeError):
            HTTPResponse().set_status(cast(int, '200'))

    @pytest.mark.parametrize('status', [99, 600])
    def test_out_of_range_status_is_rejected(self, status: int) -> None:
        with pytest.raises(ValueError):
            HTTPResponse().set_status(status)

    def test_unknown_status_uses_its_groups_reason_phrase(self) -> None:
        response = HTTPResponse(status=493)
        assert response.get_reason_phrase() == 'Bad Request'

    def test_explicit_reason_phrase_wins(self) -> None:
        response = HTTPResponse()
        response.set_status(200, reason='Fine')
        assert response.get_reason_phrase() == 'Fine'


class TestRedirect:
    def test_redirect_sets_status_location_and_plain_body(self) -> None:
        response = HTTPResponse()
        body = response.redirect('http://example.com/x')
        assert response.get_status_code() == 302
        assert response.get_header('location') == 'http://example.com/x'
        assert response.get_content_type() == 'text/plain'
        assert 'http://example.com/x' in body

    def test_permanent_redirect_is_301(self) -> None:
        response = HTTPResponse()
        response.redirect('http://example.com/x', permanent=True)
        assert response.get_status_code() == 301

    def test_non_string_location_is_rejected(self) -> None:
        with pytest.raises(TypeError):
            HTTPResponse().redirect(cast(str, 42))

    def test_location_without_scheme_is_rejected(self) -> None:
        with pytest.raises(ValueError):
            HTTPResponse().redirect('/relative/path')


class TestCookies:
    def test_expire_cookie_sends_an_already_expired_cookie(self) -> None:
        response = HTTPResponse()
        response.expire_cookie('sid', path='/')
        headers = response.generate_headers()
        cookies = [v for name, v in headers if name == 'Set-Cookie']
        assert len(cookies) == 1
        assert 'sid="deleted"' in cookies[0]
        assert 'max-age=0' in cookies[0]
        assert 'expires=Thu, 01-Jan-1970 00:00:00 GMT' in cookies[0]
        assert 'path=/' in cookies[0]

    def test_set_cookie_again_keeps_earlier_attributes(self) -> None:
        response = HTTPResponse()
        response.set_cookie('sid', 'a', path='/app')
        response.set_cookie('sid', 'b')
        headers = response.generate_headers()
        cookies = [v for name, v in headers if name == 'Set-Cookie']
        assert cookies == ['sid="b"; path=/app']


class TestContentType:
    def test_non_text_content_type_drops_the_charset(self) -> None:
        response = HTTPResponse()
        response.set_content_type('application/json')
        headers = generated_headers(response)
        assert headers['content-type'] == 'application/json'

    def test_text_content_type_keeps_the_charset(self) -> None:
        response = HTTPResponse()
        response.set_content_type('text/plain')
        headers = generated_headers(response)
        assert headers['content-type'] == 'text/plain; charset=utf-8'


class TestCaching:
    def test_set_expires_generates_max_age_and_expires(self) -> None:
        response = HTTPResponse()
        response.set_expires(hours=1)
        headers = generated_headers(response)
        assert headers['cache-control'] == 'max-age=3600'
        assert 'expires' in headers

    def test_set_expires_none_suppresses_cache_headers(self) -> None:
        response = HTTPResponse()
        response.set_expires(None)
        headers = generated_headers(response)
        assert 'cache-control' not in headers
        assert 'expires' not in headers

    def test_default_response_is_uncacheable(self) -> None:
        headers = generated_headers(HTTPResponse())
        assert headers['cache-control'] == 'max-age=0, no-cache'
        assert headers['expires'] == '-1'


class TestCompression:
    def test_compressed_body_round_trips_through_gzip(self) -> None:
        response = HTTPResponse()
        response.set_body('x' * 1000, compress=True)
        headers = generated_headers(response)
        assert headers['content-encoding'] == 'gzip'
        assert gzip.decompress(cast(bytes, response.body)) == b'x' * 1000

    def test_already_compressed_content_type_is_not_gzipped(self) -> None:
        response = HTTPResponse(content_type='image/png')
        response.set_body(b'x' * 1000, compress=True)
        assert response.get_header('content-encoding') is None
        assert response.body == b'x' * 1000


class TestJavascript:
    def test_add_javascript_collects_code_by_id(self) -> None:
        response = HTTPResponse()
        response.add_javascript('init', 'var a = 1;')
        response.add_javascript('util', 'var b = 2;')
        assert response.javascript_code == {
            'init': 'var a = 1;',
            'util': 'var b = 2;',
        }

    def test_registering_the_same_id_again_is_ignored(self) -> None:
        response = HTTPResponse()
        response.add_javascript('init', 'var a = 1;')
        response.add_javascript('init', 'var a = 2;')
        assert response.javascript_code == {'init': 'var a = 1;'}


class TestContentLength:
    def test_missing_body_has_no_length_and_closes_connection(self) -> None:
        response = HTTPResponse()
        assert response.get_content_length() is None
        headers = generated_headers(response)
        assert 'content-length' not in headers
        assert headers['connection'] == 'close'

    def test_str_body_length_is_its_encoded_byte_count(self) -> None:
        response = HTTPResponse(body='hé')
        assert response.get_content_length() == len('hé'.encode())
