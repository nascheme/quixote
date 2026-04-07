from quixote.http_request import parse_cookies


class TestParseCookies:
    def test_basic(self):
        assert parse_cookies('a') == {'a': ''}
        assert parse_cookies('a = ') == {'a': ''}
        assert parse_cookies('a = ""') == {'a': ''}
        assert parse_cookies(r'a = "\""') == {'a': '"'}
        assert parse_cookies('a, b; c') == {'a': '', 'b': '', 'c': ''}
        assert parse_cookies('a, b=1') == {'a': '', 'b': '1'}
        assert parse_cookies('a = ";, \t";') == {'a': ';, \t'}

    def test_rfc2109_example(self):
        s = (
            '$Version="1"; Customer="WILE_E_COYOTE"; $Path="/acme"; '
            'Part_Number="Rocket_Launcher_0001"; $Path="/acme"'
        )
        result = {
            'Customer': 'WILE_E_COYOTE',
            'Part_Number': 'Rocket_Launcher_0001',
        }
        assert parse_cookies(s) == result

    def test_other(self):
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

    def test_invalid(self):
        parse_cookies('a="123')
        parse_cookies('a=123"')
