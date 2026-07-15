import io

import pytest
from helpers import make_environ

from quixote.errors import RequestError
from quixote.http_request import (
    HTTPRequest,
    Upload,
    get_content_type,
    make_safe_filename,
    parse_cookies,
    parse_header,
    parse_query,
)


class TestParseCookies:
    def test_basic(self) -> None:
        assert parse_cookies('a') == {'a': ''}
        assert parse_cookies('a = ') == {'a': ''}
        assert parse_cookies('a = ""') == {'a': ''}
        assert parse_cookies(r'a = "\""') == {'a': '"'}
        assert parse_cookies('a, b; c') == {'a': '', 'b': '', 'c': ''}
        assert parse_cookies('a, b=1') == {'a': '', 'b': '1'}
        assert parse_cookies('a = ";, \t";') == {'a': ';, \t'}

    def test_rfc2109_example(self) -> None:
        s = (
            '$Version="1"; Customer="WILE_E_COYOTE"; $Path="/acme"; '
            'Part_Number="Rocket_Launcher_0001"; $Path="/acme"'
        )
        result = {
            'Customer': 'WILE_E_COYOTE',
            'Part_Number': 'Rocket_Launcher_0001',
        }
        assert parse_cookies(s) == result

    def test_other(self) -> None:
        s = 'PREF=ID=0a06b1:TM=108:LM=1069:C2COFF=1:S=ETXrcU'
        result = {'PREF': 'ID=0a06b1:TM=108:LM=1069:C2COFF=1:S=ETXrcU'}
        assert parse_cookies(s) == result
        s = 'pageColor=White; pageWidth=990; fontSize=12; fontFace=1; E=E'
        assert parse_cookies(s) == {
            'pageColor': 'White',
            'pageWidth': '990',
            'fontSize': '12',
            'fontFace': '1',
            'E': 'E',
        }
        s = 'userid="joe"; QX_session="58a3ced39dcd0d"'
        assert parse_cookies(s) == {
            'userid': 'joe',
            'QX_session': '58a3ced39dcd0d',
        }

    def test_invalid(self) -> None:
        parse_cookies('a="123')
        parse_cookies('a=123"')


class TestConstructor:
    def test_malformed_content_length_is_a_request_error(self) -> None:
        with pytest.raises(RequestError):
            HTTPRequest(None, make_environ(CONTENT_LENGTH='abc'))

    def test_https_environ_gives_the_https_scheme(self) -> None:
        request = HTTPRequest(None, make_environ(HTTPS='on'))
        assert request.get_scheme() == 'https'

    def test_default_scheme_is_http(self) -> None:
        request = HTTPRequest(None, make_environ())
        assert request.get_scheme() == 'http'


class TestGetPath:
    @pytest.mark.parametrize(
        'n,expected',
        [
            (0, '/bar/baz/qux'),
            (1, '/bar/baz'),
            (2, '/bar'),
            (-1, '/bar'),
            (-2, '/bar/baz'),
            (-3, '/bar/baz/qux'),
        ],
    )
    def test_n_drops_path_components(self, n: int, expected: str) -> None:
        request = HTTPRequest(None, make_environ(path='/bar/baz/qux'))
        assert request.get_path(n) == expected

    def test_trailing_slash_is_an_empty_last_component(self) -> None:
        request = HTTPRequest(None, make_environ(path='/bar/baz/'))
        assert request.get_path() == '/bar/baz/'
        assert request.get_path(1) == '/bar/baz'

    def test_n_larger_than_the_path_is_an_error(self) -> None:
        request = HTTPRequest(None, make_environ(path='/bar'))
        with pytest.raises(ValueError):
            request.get_path(2)


class TestGetUrl:
    def test_url_is_rebuilt_from_scheme_server_and_path(self) -> None:
        request = HTTPRequest(None, make_environ(path='/a b'))
        assert request.get_url() == 'http://example.com/a%20b'

    def test_http_host_header_wins_over_server_name(self) -> None:
        environ = make_environ(HTTP_HOST='override.example.org')
        request = HTTPRequest(None, environ)
        assert request.get_server() == 'override.example.org'

    def test_default_port_is_omitted_from_the_server(self) -> None:
        request = HTTPRequest(None, make_environ())
        assert request.get_server() == 'example.com'

    def test_non_default_port_is_kept_in_the_server(self) -> None:
        request = HTTPRequest(None, make_environ(SERVER_PORT='8080'))
        assert request.get_server() == 'example.com:8080'


class TestGetHeader:
    @pytest.mark.parametrize(
        'name', ['User-Agent', 'user-agent', 'HTTP_USER_AGENT']
    )
    def test_header_spellings_are_equivalent(self, name: str) -> None:
        request = HTTPRequest(None, make_environ(HTTP_USER_AGENT='test/1.0'))
        assert request.get_header(name) == 'test/1.0'

    def test_missing_header_returns_the_default(self) -> None:
        request = HTTPRequest(None, make_environ())
        assert request.get_header('X-Missing', 'dflt') == 'dflt'


class TestProcessInputs:
    def test_query_string_populates_the_form(self) -> None:
        environ = make_environ(query='a=1&a=2&b=x')
        request = HTTPRequest(None, environ)
        request.process_inputs()
        assert request.get_field('a') == ['1', '2']
        assert request.get_field('b') == 'x'
        assert request.get_field('missing', 'dflt') == 'dflt'

    def test_urlencoded_post_body_populates_the_form(self) -> None:
        body = b'a=1&b=h%C3%A9'
        environ = make_environ(
            method='POST',
            CONTENT_TYPE='application/x-www-form-urlencoded',
            CONTENT_LENGTH=str(len(body)),
        )
        request = HTTPRequest(io.BytesIO(body), environ)
        request.process_inputs()
        assert request.get_field('a') == '1'
        assert request.get_field('b') == 'hé'

    def test_truncated_post_body_is_a_request_error(self) -> None:
        environ = make_environ(
            method='POST',
            CONTENT_TYPE='application/x-www-form-urlencoded',
            CONTENT_LENGTH='100',
        )
        request = HTTPRequest(io.BytesIO(b'a=1'), environ)
        with pytest.raises(RequestError):
            request.process_inputs()

    def test_multipart_body_gives_str_fields_and_uploads(self) -> None:
        body = (
            b'--BOUND\r\n'
            b'Content-Disposition: form-data; name="note"\r\n'
            b'\r\n'
            b'hello\r\n'
            b'--BOUND\r\n'
            b'Content-Disposition: form-data; name="doc"; '
            b'filename="f.txt"\r\n'
            b'Content-Type: text/plain\r\n'
            b'\r\n'
            b'payload\r\n'
            b'--BOUND--\r\n'
        )
        environ = make_environ(
            method='POST',
            CONTENT_TYPE='multipart/form-data; boundary=BOUND',
            CONTENT_LENGTH=str(len(body)),
        )
        request = HTTPRequest(io.BytesIO(body), environ)
        request.process_inputs()
        assert request.get_field('note') == 'hello'
        upload = request.get_field('doc')
        assert isinstance(upload, Upload)
        assert upload.base_filename == 'f.txt'
        assert upload.read() == b'payload'


class TestParseQuery:
    def test_plus_and_percent_escapes_are_decoded(self) -> None:
        fields = parse_query('name=J.+R.&city=S%C3%A3o', 'utf-8')
        assert fields == {'name': 'J. R.', 'city': 'São'}

    def test_repeated_names_collect_into_a_list(self) -> None:
        assert parse_query('a=1&a=2', 'utf-8') == {'a': ['1', '2']}

    def test_bare_name_maps_to_an_empty_value(self) -> None:
        assert parse_query('flag', 'utf-8') == {'flag': ''}


class TestParseHeader:
    def test_value_and_parameters_are_split(self) -> None:
        value, params = parse_header('text/html; charset=utf-8')
        assert value == 'text/html'
        assert params == {'charset': 'utf-8'}

    def test_quoted_parameter_values_are_unquoted(self) -> None:
        _value, params = parse_header('form-data; name="a b"')
        assert params == {'name': 'a b'}


class TestGetContentType:
    def test_parameters_are_stripped_from_the_media_type(self) -> None:
        environ = {'CONTENT_TYPE': 'text/html; charset=utf-8'}
        assert get_content_type(environ) == 'text/html'

    def test_missing_content_type_is_none(self) -> None:
        assert get_content_type({}) is None


class TestMakeSafeFilename:
    def test_unsafe_characters_become_underscores(self) -> None:
        assert make_safe_filename('a/b:c*d.txt') == 'a_b_c_d.txt'

    def test_safe_characters_are_kept(self) -> None:
        name = 'report 2024-01.txt'
        assert make_safe_filename(name) == name
