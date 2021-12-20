"""quixote.http_request

Provides the HTTPRequest class and related code for parsing HTTP
requests, such as the Upload class.
"""

import re
import os
import tempfile
import urllib.request, urllib.parse, urllib.error
import email
import io

import quixote
from quixote.http_response import HTTPResponse
from quixote.errors import RequestError


# Various regexes for parsing specific bits of HTTP, all from RFC 2616.

# These are needed by 'get_encoding()', to parse the "Accept-Encoding"
# header.  LWS is linear whitespace; the latter two assume that LWS
# has been removed.
_http_lws_re = re.compile(r"(\r\n)?[ \t]+")
_http_list_re = re.compile(r",+")
_http_encoding_re = re.compile(r"([^;]+)(;q=([\d.]+))?$")

# These are needed by 'guess_browser_version()', for parsing the
# "User-Agent" header.
#   token = 1*<any CHAR except CTLs or separators>
#   CHAR = any 7-bit US ASCII character (0-127)
#   separators are  ( ) < > @ , ; : \ " / [ ] ? = { }
#
# The user_agent RE is a simplification; it only looks for one "product",
# possibly followed by a comment.
_http_token_pat = r"[\w!#$%&'*+.^`|~-]+"
_http_product_pat = r'(%s)(?:/(%s))?' % (_http_token_pat, _http_token_pat)
_http_product_re = re.compile(_http_product_pat)
_comment_delim_re = re.compile(r';\s*')


def get_content_type(environ):
    ctype = environ.get("CONTENT_TYPE")
    if ctype:
        return ctype.split(";")[0]
    else:
        return None


def _decode_string(s, charset):
    try:
        return s.decode(charset)
    except LookupError:
        raise RequestError('unknown charset %r' % charset)
    except UnicodeDecodeError:
        raise RequestError('invalid %r encoded string' % charset)


def parse_header(line):
    """Parse a Content-type like header.

    Return the main content-type and a dictionary of options.

    """
    if isinstance(line, email.header.Header):  # file upload
        line = ''.join(val for val, charset in line._chunks)
    plist = [val.strip() for val in line.split(';')]
    key = plist.pop(0).lower()
    pdict = {}
    for p in plist:
        i = p.find('=')
        if i >= 0:
            name = p[:i].strip().lower()
            value = p[i + 1 :].strip()
            if len(value) >= 2 and value[0] == value[-1] == '"':
                value = value[1:-1]
            pdict[name] = value
    return key, pdict


def parse_content_disposition(full_cdisp):
    (cdisp, cdisp_params) = parse_header(full_cdisp)
    name = cdisp_params.get('name')
    if not (cdisp == 'form-data' and name):
        raise RequestError(
            'expected Content-Disposition: form-data '
            'with a "name" parameter: got %r' % full_cdisp
        )
    return (name, cdisp_params.get('filename'))


def parse_query(qs, charset):
    """(qs: string) -> {key:string, string|[string]}

    Parse a query given as a string argument and return a dictionary.
    """
    fields = {}
    for chunk in qs.split('&'):
        if not chunk:
            continue
        if '=' not in chunk:
            name = chunk
            value = ''
        else:
            name, value = chunk.split('=', 1)
        try:
            name = urllib.parse.unquote_plus(
                name, encoding=charset, errors='strict'
            )
            value = urllib.parse.unquote_plus(
                value, encoding=charset, errors='strict'
            )
        except LookupError:
            raise RequestError('unknown charset %r' % charset)
        except UnicodeDecodeError:
            raise RequestError('invalid %r encoded string' % charset)
        _add_field_value(fields, name, value)
    return fields


def _add_field_value(fields, name, value):
    if name in fields:
        values = fields[name]
        if not isinstance(values, list):
            fields[name] = values = [values]
        values.append(value)
    else:
        fields[name] = value


class HTTPRequest:
    """
    Model a single HTTP request and all associated data: environment
    variables, form variables, cookies, etc.

    To access environment variables associated with the request, use
    get_environ(): eg. request.get_environ('SERVER_PORT', 80).

    To access form variables, use get_field(), eg.
    request.get_field("name").

    To access cookies, use get_cookie().

    Various bits and pieces of the requested URL can be accessed with
    get_url(), get_path(), get_server()

    The HTTPResponse object corresponding to this request is available
    in the 'response' attribute.  This is rarely needed: eg. to send an
    error response, you should raise one of the exceptions in errors.py;
    to send a redirect, you should use the quixote.redirect() function,
    which lets you specify relative URLs.  However, if you need to tweak
    the response object in other ways, you can do so via 'response'.
    Just keep in mind that Quixote discards the original response object
    when handling an exception.
    """

    DEFAULT_CHARSET = None  # defaults to quixote.DEFAULT_CHARSET

    def __init__(self, stdin, environ, seekable=False):
        self.stdin = stdin
        self._stdin = None  # set after stdin is buffered to temp file
        self.body_is_seekable = seekable
        self.environ = environ
        self.form = {}
        self.session = None
        self.charset = self.DEFAULT_CHARSET or quixote.DEFAULT_CHARSET
        self.response = HTTPResponse()

        length = environ.get('CONTENT_LENGTH') or 0
        try:
            self._content_length = int(length)
        except ValueError:
            raise RequestError('invalid content-length header')

        # The strange treatment of SERVER_PORT_SECURE is because IIS
        # sets this environment variable to "0" for non-SSL requests
        # (most web servers -- well, Apache at least -- simply don't set
        # it in that case).
        if (
            environ.get('HTTPS', 'off').lower() in ('on', 'yes', '1')
            or environ.get('SERVER_PORT_SECURE', '0') != '0'
        ):
            self.scheme = "https"
        else:
            self.scheme = "http"

        k = self.environ.get('HTTP_COOKIE', '')
        if k:
            self.cookies = parse_cookies(k)
        else:
            self.cookies = {}

        # IIS breaks PATH_INFO because it leaves in the path to
        # the script, so SCRIPT_NAME is "/cgi-bin/q.py" and PATH_INFO
        # is "/cgi-bin/q.py/foo/bar".  The following code fixes
        # PATH_INFO to the expected value "/foo/bar".
        web_server = environ.get('SERVER_SOFTWARE', 'unknown')
        if web_server.find('Microsoft-IIS') != -1:
            script = environ['SCRIPT_NAME']
            path = environ['PATH_INFO']
            if path.startswith(script):
                path = path[len(script) :]
                self.environ['PATH_INFO'] = path

    def make_body_seekable(self):
        """Ensure that 'stdin' is a seekable file object."""
        if self.body_is_seekable:
            self.stdin.seek(0)
            return
        if self._content_length < 20000:
            fp = io.BytesIO()
        else:
            fp = tempfile.TemporaryFile("w+b")
        remaining = self._content_length
        while remaining > 0:
            s = self.stdin.read(min(remaining, 10000))
            if not s:
                raise RequestError('unexpected end of request body')
            fp.write(s)
            remaining -= len(s)
        fp.seek(0)
        self._stdin = self.stdin
        self.stdin = fp
        self.body_is_seekable = True

    def process_inputs(self):
        self.make_body_seekable()
        # In the case of a database conflict, process_inputs() might
        # be called more than once.  In this case, there is no need
        # to buffer stdin but reset the form data and input file.
        self.form.clear()
        query = self.get_query()
        if query:
            self.form.update(parse_query(query, self.charset))
        ctype = self.environ.get("CONTENT_TYPE")
        if ctype:
            ctype, ctype_params = parse_header(ctype)
            if ctype == 'application/x-www-form-urlencoded':
                self._process_urlencoded(self._content_length, ctype_params)
            elif ctype == 'multipart/form-data':
                self._process_multipart(self._content_length, ctype_params)

    def _process_urlencoded(self, length, params):
        query = self.stdin.read(length)
        if len(query) != length:
            raise RequestError('unexpected end of request body')
        # Use the declared charset if it's provided (most browser's don't
        # provide it to avoid breaking old HTTP servers).
        charset = params.get('charset', self.charset)
        # should contain only ASCII characters but parse as iso-8859-1
        query = query.decode('iso-8859-1')
        self.form.update(parse_query(query, charset))

    def _process_multipart(self, length, params):
        boundary = params.get('boundary')
        if not boundary:
            raise RequestError('multipart/form-data missing boundary')
        charset = params.get('charset')
        mimeinput = MIMEInput(self.stdin, boundary, length)
        try:
            for _line in mimeinput.readpart():
                pass  # discard lines up to first boundary
            while mimeinput.moreparts():
                self._process_multipart_body(mimeinput, charset)
        except EOFError:
            raise RequestError('unexpected end of multipart/form-data')

    def _process_multipart_body(self, mimeinput, charset):
        headers = io.BytesIO()
        lines = mimeinput.readpart()
        for line in lines:
            headers.write(line)
            if line == b'\r\n':
                break
        headers.seek(0)
        headers = email.message_from_binary_file(headers)
        ctype, ctype_params = parse_header(headers.get('content-type', ''))
        if ctype and 'charset' in ctype_params:
            charset = ctype_params['charset']
        cdisp, cdisp_params = parse_header(
            headers.get('content-disposition', '')
        )
        if not cdisp:
            raise RequestError('expected Content-Disposition header')
        name = cdisp_params.get('name')
        filename = cdisp_params.get('filename')
        if not (cdisp == 'form-data' and name):
            raise RequestError(
                'expected Content-Disposition: form-data'
                'with a "name" parameter: got %r'
                % headers.get('content-disposition', '')
            )
        # FIXME: should really to handle Content-Transfer-Encoding and other
        # MIME complexity here.  See RFC2048 for the full horror story.
        if filename:
            # it might be large file upload so use a temporary file
            upload = Upload(filename, ctype, charset)
            upload.receive(lines)
            _add_field_value(self.form, name, upload)
        else:
            value = _decode_string(b''.join(lines), charset or self.charset)
            _add_field_value(self.form, name, value)

    def get_header(self, name, default=None):
        """get_header(name : string, default : string = None) -> string

        Return the named HTTP header, or an optional default argument
        (or None) if the header is not found.  Note that both original
        and CGI-ified header names are recognized, e.g. 'Content-Type',
        'CONTENT_TYPE' and 'HTTP_CONTENT_TYPE' should all return the
        Content-Type header, if available.
        """
        environ = self.environ
        name = name.replace("-", "_").upper()
        val = environ.get(name)
        if val is not None:
            return val
        if name[:5] != 'HTTP_':
            name = 'HTTP_' + name
        return environ.get(name, default)

    def get_cookie(self, cookie_name, default=None):
        return self.cookies.get(cookie_name, default)

    def get_cookies(self):
        return self.cookies

    def get_field(self, name, default=None):
        return self.form.get(name, default)

    def get_fields(self):
        return self.form

    def get_method(self):
        """Returns the HTTP method for this request"""
        return self.environ.get('REQUEST_METHOD', 'GET')

    def formiter(self):
        return self.form.items()

    def get_scheme(self):
        return self.scheme

    # The following environment variables are useful for reconstructing
    # the original URL, all of which are specified by CGI 1.1:
    #
    #   SERVER_NAME            "www.example.com"
    #   SCRIPT_NAME            "/q"
    #   PATH_INFO              "/debug/dump_sessions"
    #   QUERY_STRING           "session_id=10.27.8.40...."

    def get_server(self):
        """get_server() -> string

        Return the server name with an optional port number, eg.
        "www.example.com" or "foo.bar.com:8000".
        """
        http_host = self.environ.get("HTTP_HOST")
        if http_host:
            return http_host
        server_name = self.environ["SERVER_NAME"].strip()
        server_port = self.environ.get("SERVER_PORT")
        if (
            not server_port
            or (self.get_scheme() == "http" and server_port == "80")
            or (self.get_scheme() == "https" and server_port == "443")
        ):
            return server_name
        else:
            return server_name + ":" + server_port

    def get_path(self, n=0):
        """get_path(n : int = 0) -> string

        Return the path of the current request, chopping off 'n' path
        components from the right.  Eg. if the path is "/bar/baz/qux",
        n=0 would return "/bar/baz/qux" and n=2 would return "/bar".
        Note that the query string, if any, is not included.

        A path with a trailing slash should just be considered as having
        an empty last component.  Eg. if the path is "/bar/baz/", then:
          get_path(0) == "/bar/baz/"
          get_path(1) == "/bar/baz"
          get_path(2) == "/bar"

        If 'n' is negative, then components from the left of the path
        are returned.  Continuing the above example,
          get_path(-1) = "/bar"
          get_path(-2) = "/bar/baz"
          get_path(-3) = "/bar/baz/"

        Raises ValueError if absolute value of n is larger than the number of
        path components."""

        path_info = self.environ.get('PATH_INFO', '')
        path = self.environ['SCRIPT_NAME'] + path_info
        if n == 0:
            return path
        else:
            path_comps = path.split('/')
            if abs(n) > len(path_comps) - 1:
                raise ValueError("n=%d too big for path '%s'" % (n, path))
            if n > 0:
                return '/'.join(path_comps[:-n])
            elif n < 0:
                return '/'.join(path_comps[: -n + 1])
            else:
                assert 0, "Unexpected value for n (%s)" % n

    def get_query(self):
        """() -> string

        Return the query component of the URL.
        """
        return self.environ.get('QUERY_STRING', '')

    def get_path_query(self):
        """() -> string

        Return the path and the query string (if any).
        """
        path = self.get_path()
        query = self.get_query()
        if query:
            path += '?' + query
        return path

    def get_url(self, n=0):
        """get_url(n : int = 0) -> string

        Return the URL of the current request, chopping off 'n' path
        components from the right.  Eg. if the URL is
        "http://foo.com/bar/baz/qux", n=2 would return
        "http://foo.com/bar".  Does not include the query string (if
        any).
        """
        return "%s://%s%s" % (
            self.get_scheme(),
            self.get_server(),
            urllib.parse.quote(self.get_path(n)),
        )

    def get_environ(self, key, default=None):
        """get_environ(key : string) -> string

        Fetch a CGI environment variable from the request environment.
        See http://hoohoo.ncsa.uiuc.edu/cgi/env.html
        for the variables specified by the CGI standard.
        """
        return self.environ.get(key, default)

    def get_encoding(self, encodings):
        """get_encoding(encodings : [string]) -> string

        Parse the "Accept-encoding" header. 'encodings' is a list of
        encodings supported by the server sorted in order of preference.
        The return value is one of 'encodings' or None if the client
        does not accept any of the encodings.
        """
        accept_encoding = self.get_header("accept-encoding") or ""
        found_encodings = self._parse_pref_header(accept_encoding)
        if found_encodings:
            for encoding in encodings:
                if encoding in found_encodings:
                    return encoding
        return None

    def get_accepted_types(self):
        """get_accepted_types() : {string:float}
        Return a dictionary mapping MIME types the client will accept
        to the corresponding quality value (1.0 if no value was specified).
        """
        accept_types = self.environ.get('HTTP_ACCEPT', "")
        return self._parse_pref_header(accept_types)

    def _parse_pref_header(self, S):
        """_parse_pref_header(S:string) : {string:float}
        Parse a list of HTTP preferences (content types, encodings) and
        return a dictionary mapping strings to the quality value.
        """

        found = {}
        # remove all linear whitespace
        S = _http_lws_re.sub("", S)
        for coding in _http_list_re.split(S):
            m = _http_encoding_re.match(coding)
            if m:
                encoding = m.group(1).lower()
                q = m.group(3) or 1.0
                try:
                    q = float(q)
                except ValueError:
                    continue
                if encoding == "*":
                    continue  # stupid, ignore it
                if q > 0:
                    found[encoding] = q
        return found

    def dump(self):
        result = []
        row = '%-15s %s'

        result.append("Form:")
        for k, v in sorted(self.form.items()):
            result.append(row % (k, v))

        result.append("")
        result.append("Cookies:")
        for k, v in sorted(self.cookies.items()):
            result.append(row % (k, v))

        result.append("")
        result.append("Environment:")
        for k, v in sorted(self.environ.items()):
            result.append(row % (k, v))
        return "\n".join(result)

    def guess_browser_version(self):
        """guess_browser_version() -> (name : string, version : string)

        Examine the User-agent request header to try to figure out what
        the current browser is.  Returns either (name, version) where
        each element is a string, (None, None) if we couldn't parse the
        User-agent header at all, or (name, None) if we got the name but
        couldn't figure out the version.

        Handles Microsoft's little joke of pretending to be Mozilla,
        eg. if the "User-Agent" header is
          Mozilla/5.0 (compatible; MSIE 5.5)
        returns ("MSIE", "5.5").  Konqueror does the same thing, and
        it's handled the same way.
        """
        ua = self.get_header('user-agent')
        if ua is None:
            return (None, None)

        # The syntax for "User-Agent" in RFC 2616 is fairly simple:
        #
        #  User-Agent      = "User-Agent" ":" 1*( product | comment )
        #  product         = token ["/" product-version ]
        #  product-version = token
        #  comment         = "(" *( ctext | comment ) ")"
        #  ctext           = <any TEXT excluding "(" and ")">
        #  token           = 1*<any CHAR except CTLs or tspecials>
        #  tspecials       = "(" | ")" | "<" | ">" | "@" | "," | ";" | ":" |
        #                    "\" | <"> | "/" | "[" | "]" | "?" | "=" | "{" |
        #                    "}" | SP | HT
        #
        # This function handles the most-commonly-used subset of this syntax,
        # namely
        #   User-Agent = "User-Agent" ":" product 1*SP [comment]
        # ie. one product string followed by an optional comment;
        # anything after that first comment is ignored.  This should be
        # enough to distinguish Mozilla/Netscape, MSIE, Opera, and
        # Konqueror.

        m = _http_product_re.match(ua)
        if not m:
            import sys

            sys.stderr.write("couldn't parse User-Agent header: %r\n" % ua)
            return (None, None)

        name, version = m.groups()
        ua = ua[m.end() :].lstrip()

        if ua.startswith('('):
            # we need to handle nested comments since MSIE uses them
            depth = 1
            chars = []
            for c in ua[1:]:
                if c == '(':
                    depth += 1
                elif c == ')':
                    depth -= 1
                    if depth == 0:
                        break
                elif depth == 1:
                    # nested comments are discarded
                    chars.append(c)
            comment = ''.join(chars)
        else:
            comment = ''
        if comment:
            comment_chunks = _comment_delim_re.split(comment)
        else:
            comment_chunks = []

        if (
            "compatible" in comment_chunks
            and len(comment_chunks) > 1
            and comment_chunks[1]
        ):
            # A-ha!  Someone is kidding around, pretending to be what
            # they are not.  Most likely MSIE masquerading as Mozilla,
            # but lots of other clients (eg. Konqueror) do the same.
            real_ua = comment_chunks[1]
            if "/" in real_ua:
                (name, version) = real_ua.split("/", 1)
            else:
                if real_ua.startswith("MSIE") and ' ' in real_ua:
                    (name, version) = real_ua.split(" ", 1)
                else:
                    name = real_ua
                    version = None
            return (name, version)

        # Either nobody is pulling our leg, or we didn't find anything
        # that looks vaguely like a user agent in the comment.  So use
        # what we found outside the comment, ie. what the spec says we
        # should use (sigh).
        return (name, version)

    # guess_browser_version ()


# See RFC 2109 for details.  Note that this parser is more liberal.
_COOKIE_RE = re.compile(
    r"""
                \s*
                (?P<name>[^=;,\s]+)
                \s*
                (
                    =
                    \s*
                    (
                        (?P<qvalue> "(\\[\x00-\x7f] | [^"])*")
                        |
                        (?P<value> [^";,\s]*)
                    )
                )?
                \s*
                [;,]?
                """,
    re.VERBOSE,
)


def parse_cookies(text):
    result = {}
    for m in _COOKIE_RE.finditer(text):
        name = m.group('name')
        if name[0] == '$':
            # discard, we don't handle per cookie attributes (e.g. $Path)
            continue
        qvalue = m.group('qvalue')
        if qvalue:
            value = re.sub(r'\\(.)', r'\1', qvalue)[1:-1]
        else:
            value = m.group('value') or ''
        result[name] = value
    return result


# characters considered safe in a filename
_SAFE_PAT = re.compile(r'[^\w@&+=., -]')


def make_safe_filename(s):
    return _SAFE_PAT.sub('_', s)


class Upload:
    r"""
    Represents a single uploaded file.  Uploaded files live in the
    filesystem, *not* in memory.

      fp
        an open file containing the content of the upload.  The file pointer
        points to the beginning of the file
      orig_filename
        the complete filename supplied by the user-agent in the
        request that uploaded this file.  Depending on the browser,
        this might have the complete path of the original file
        on the client system, in the client system's syntax -- eg.
        "C:\foo\bar\upload_this" or "/foo/bar/upload_this" or
        "foo:bar:upload_this".
      base_filename
        the base component of orig_filename, shorn of MS-DOS,
        Mac OS, and Unix path components and with "unsafe"
        characters neutralized (see make_safe_filename())
      content_type
        the content type provided by the user-agent in the request
        that uploaded this file.
      charset
        the charset provide by the user-agent
    """

    def __init__(self, orig_filename, content_type=None, charset=None):
        if orig_filename:
            self.orig_filename = orig_filename
            bspos = orig_filename.rfind("\\")
            cpos = orig_filename.rfind(":")
            spos = orig_filename.rfind("/")
            if bspos != -1:  # eg. "\foo\bar" or "D:\ding\dong"
                filename = orig_filename[bspos + 1 :]
            elif cpos != -1:  # eg. "C:foo" or ":ding:dong:foo"
                filename = orig_filename[cpos + 1 :]
            elif spos != -1:  # eg. "foo/bar/baz" or "/tmp/blah"
                filename = orig_filename[spos + 1 :]
            else:
                filename = orig_filename

            self.base_filename = make_safe_filename(filename)
        else:
            self.orig_filename = None
            self.base_filename = None
        self.content_type = content_type
        self.charset = charset
        self.fp = None

    def receive(self, lines):
        self.fp = tempfile.TemporaryFile("w+b")
        for line in lines:
            self.fp.write(line)
        self.fp.seek(0)

    def __str__(self):
        return str(self.orig_filename)

    def __repr__(self):
        return "<%s at %x: %s>" % (self.__class__.__name__, id(self), self)

    def read(self, n):
        return self.fp.read(n)

    def readline(self):
        return self.fp.readline()

    def readlines(self):
        return self.fp.readlines()

    def __iter__(self):
        return iter(self.fp)

    def close(self):
        self.fp.close()

    def get_size(self):
        """Return the size of the file, in bytes."""
        if self.fp is None:
            return 0
        else:
            return os.fstat(self.fp.fileno()).st_size


class LineInput:
    r"""
    A wrapper for an input stream that has the following properties:

        * lines are terminated by \r\n

        * lines shorter than 'maxlength' are always returned unbroken

        * lines longer than 'maxlength' are broken but the pair of
          characters \r\n are never split

        * no more than 'length' characters are read from the underlying
          stream

        * if the underlying stream does not produce at least 'length'
          characters then EOFError is raised

    """

    def __init__(self, fp, length):
        self.fp = fp
        self.length = length
        self.buf = b''

    def readline(self, maxlength=4096):
        # fill buffer
        n = min(self.length, maxlength - len(self.buf))
        if n > 0:
            self.length -= n
            assert self.length >= 0
            chunk = self.fp.read(n)
            if len(chunk) != n:
                raise EOFError('unexpected end of input')
            self.buf += chunk
        # split into lines
        buf = self.buf
        i = buf.find(b'\r\n')
        if i >= 0:
            i += 2
            self.buf = buf[i:]
            return buf[:i]
        elif buf.endswith(b'\r'):
            # avoid splitting CR LF pairs
            self.buf = b'\r'
            return buf[:-1]
        else:
            self.buf = b''
            return buf


class MIMEInput:
    """
    Split a MIME input stream into parts.  Note that this class does not
    handle headers, transfer encoding, etc.
    """

    def __init__(self, fp, boundary, length):
        self.lineinput = LineInput(fp, length)
        self.pat = b'--' + boundary.encode('iso-8859-1')
        self.done = False

    def moreparts(self):
        """Return true if there are more parts to be read."""
        return not self.done

    def readpart(self):
        """Generate all the lines up to a MIME boundary.  Note that you
        must exhaust the generator before calling this function again."""
        assert not self.done
        last_line = b''
        while 1:
            line = self.lineinput.readline()
            if not line:
                # Hit EOF -- nothing more to read.  This should *not* happen
                # in a well-formed MIME message.
                raise EOFError('MIME boundary not found (end of input)')
            # FIXME: check this
            if last_line.endswith(b'\r\n') or last_line == b'':
                if line.startswith(self.pat):
                    # If we hit the boundary line, return now. Forget
                    # the current line *and* the CRLF ending of the
                    # previous line.
                    if line.startswith(self.pat + b'--'):
                        # hit final boundary
                        self.done = True
                    yield last_line[:-2]
                    return
            if last_line:
                yield last_line
            last_line = line
