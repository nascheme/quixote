"""Tests for the quixote.util helpers and static-file classes."""

from collections.abc import Iterator
from pathlib import Path

import pytest
from helpers import call, request_context

import quixote
from quixote.directory import Directory
from quixote.publish import Publisher
from quixote.util import (
    FileStream,
    MemoryFile,
    Redirector,
    StaticDirectory,
    StaticFile,
    dump_request,
    get_directory_path,
    import_object,
    randbytes,
    safe_str_cmp,
)
from quixote.wsgi import QWIP


class TestRandbytes:
    def test_returns_a_random_text_token(self) -> None:
        token = randbytes(8)
        assert isinstance(token, str)
        assert token != ''
        assert randbytes(8) != token


class TestSafeStrCmp:
    def test_equal_strings_compare_equal(self) -> None:
        assert safe_str_cmp('secret', 'secret') is True
        assert safe_str_cmp(b'secret', b'secret') is True

    def test_different_strings_compare_unequal(self) -> None:
        assert safe_str_cmp('secret', 'other') is False
        assert safe_str_cmp('secret', 'secret2') is False

    def test_mixed_str_and_bytes_are_rejected(self) -> None:
        with pytest.raises(TypeError):
            safe_str_cmp('secret', b'secret')


class TestImportObject:
    def test_a_dotted_name_resolves_to_the_attribute(self) -> None:
        assert import_object('quixote.util.randbytes') is randbytes

    def test_a_missing_module_raises(self) -> None:
        with pytest.raises(ImportError):
            import_object('quixote.no_such_module.thing')


class TestFileStream:
    def test_streams_the_file_contents_in_chunks(
        self, tmp_path: Path
    ) -> None:
        data = b'x' * (FileStream.CHUNK_SIZE + 10)
        path = tmp_path / 'data.bin'
        path.write_bytes(data)
        with open(path, 'rb') as fp:
            stream = FileStream(fp, size=len(data))
            chunks = list(stream)
        assert b''.join(chunks) == data
        assert len(chunks) == 2
        assert stream.length == len(data)


class TestStaticFile:
    def test_a_relative_path_is_rejected(self) -> None:
        with pytest.raises(ValueError):
            StaticFile('relative/path.txt')

    def test_serves_the_file_with_type_and_last_modified(
        self, publisher: Publisher, tmp_path: Path
    ) -> None:
        path = tmp_path / 'hello.txt'
        path.write_bytes(b'hello static')
        with request_context(publisher) as request:
            body = StaticFile(str(path))()
            assert isinstance(body, FileStream)
            assert b''.join(body) == b'hello static'
            response = request.response
        assert response.get_content_type() == 'text/plain'
        assert response.get_header('last-modified') is not None

    def test_matching_if_modified_since_is_a_304(
        self, publisher: Publisher, tmp_path: Path
    ) -> None:
        path = tmp_path / 'hello.txt'
        path.write_bytes(b'hello static')
        with request_context(publisher) as request:
            StaticFile(str(path))()
            last_modified = request.response.get_header('last-modified')
        assert isinstance(last_modified, str)
        with request_context(
            publisher, HTTP_IF_MODIFIED_SINCE=last_modified
        ) as request:
            body = StaticFile(str(path))()
            assert body == ''
            assert request.response.get_status_code() == 304


class TestMemoryFile:
    def test_serves_its_data_with_the_given_type(
        self, publisher: Publisher
    ) -> None:
        memory_file = MemoryFile('body { }', mime_type='text/css')
        with request_context(publisher) as request:
            assert memory_file() == 'body { }'
            assert request.response.get_content_type() == 'text/css'
        assert memory_file.get_data() == b'body { }'


class TestRedirector:
    def test_redirects_any_path_beneath_it(
        self, publisher: Publisher
    ) -> None:
        redirector = Redirector('http://elsewhere.org/')
        assert redirector._q_lookup('deeper') is redirector
        with request_context(publisher) as request:
            redirector()
            response = request.response
        assert response.get_status_code() == 302
        assert response.get_header('location') == 'http://elsewhere.org/'


class TestDumpRequest:
    def test_dumps_form_cookies_and_environ_as_html(
        self, publisher: Publisher
    ) -> None:
        with request_context(publisher, HTTP_COOKIE='sid=abc') as request:
            request.form['field'] = 'field value'
            html = str(dump_request(request))
        assert 'field value' in html
        assert 'sid' in html
        assert 'SERVER_NAME' in html


@pytest.fixture
def static_app(tmp_path: Path) -> Iterator[QWIP]:
    """A WSGI app serving `tmp_path` under /static."""
    (tmp_path / 'hello.txt').write_bytes(b'hello static')
    (tmp_path / 'sub').mkdir()

    class Root(Directory):
        _q_exports = ['static', 'where']

        def __init__(self) -> None:
            self.static = StaticDirectory(
                str(tmp_path), list_directory=True
            )

        def where(self) -> str:
            path = get_directory_path()
            return ','.join(type(obj).__name__ for obj in path)

    Publisher(Root())
    try:
        yield quixote.get_wsgi_app()
    finally:
        quixote.cleanup()


class TestStaticDirectory:
    def test_serves_an_existing_file(self, static_app: QWIP) -> None:
        status, headers, body = call(static_app, '/static/hello.txt')
        assert status == '200 OK'
        assert body == b'hello static'
        assert headers['Content-Type'].startswith('text/plain')

    def test_a_missing_file_is_not_found(self, static_app: QWIP) -> None:
        status, _headers, _body = call(static_app, '/static/missing.txt')
        assert status.startswith('404')

    def test_dot_dot_traversal_is_blocked(self, static_app: QWIP) -> None:
        status, _headers, _body = call(static_app, '/static/..')
        assert status.startswith('404')

    def test_the_index_lists_files_and_subdirectories(
        self, static_app: QWIP
    ) -> None:
        status, _headers, body = call(static_app, '/static/')
        assert status == '200 OK'
        assert b'<a href="hello.txt">hello.txt</a>' in body
        assert b'<a href="sub">sub</a>/' in body


class TestGetDirectoryPath:
    def test_returns_the_traversed_directory_instances(
        self, static_app: QWIP
    ) -> None:
        _status, _headers, body = call(static_app, '/where')
        assert body == b'Root'
