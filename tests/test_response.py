from collections.abc import Iterable

from quixote.http_response import HTTPResponse, Stream


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
