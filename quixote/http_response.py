"""quixote.http_response

Provides the HTTPResponse class.
"""

import time
try:
    import zlib
except ImportError:
    pass
import struct
from email.utils import formatdate
import quixote
from quixote.html import stringify

status_reasons = {
    100: 'Continue',
    101: 'Switching Protocols',
    102: 'Processing',
    200: 'OK',
    201: 'Created',
    202: 'Accepted',
    203: 'Non-Authoritative Information',
    204: 'No Content',
    205: 'Reset Content',
    206: 'Partial Content',
    207: 'Multi-Status',
    300: 'Multiple Choices',
    301: 'Moved Permanently',
    302: 'Moved Temporarily',
    303: 'See Other',
    304: 'Not Modified',
    305: 'Use Proxy',
    307: 'Temporary Redirect',
    400: 'Bad Request',
    401: 'Unauthorized',
    402: 'Payment Required',
    403: 'Forbidden',
    404: 'Not Found',
    405: 'Method Not Allowed',
    406: 'Not Acceptable',
    407: 'Proxy Authentication Required',
    408: 'Request Time-out',
    409: 'Conflict',
    410: 'Gone',
    411: 'Length Required',
    412: 'Precondition Failed',
    413: 'Request Entity Too Large',
    414: 'Request-URI Too Large',
    415: 'Unsupported Media Type',
    416: 'Requested range not satisfiable',
    417: 'Expectation Failed',
    422: 'Unprocessable Entity',
    423: 'Locked',
    424: 'Failed Dependency',
    500: 'Internal Server Error',
    501: 'Not Implemented',
    502: 'Bad Gateway',
    503: 'Service Unavailable',
    504: 'Gateway Time-out',
    505: 'HTTP Version not supported',
    507: 'Insufficient Storage',
}

_GZIP_HEADER = (b"\037\213" # magic
                b"\010" # compression method
                b"\000" # flags
                b"\000\000\000\000" # time, who cares?
                b"\002"
                b"\377")

# content that is already compressed, don't bother trying
_GZIP_EXCLUDE = set(["application/pdf",
                     "application/zip",
                     "audio/mpeg",
                     "image/gif",
                     "image/jpeg",
                     "image/png",
                     "video/mpeg",
                     "video/quicktime",
                     "video/x-msvideo",
                     ])

def _LOWU32(i):
    return i & 0xFFFFFFFF

class HTTPResponse:
    """
    An object representation of an HTTP response.

    The Response type encapsulates all possible responses to HTTP
    requests.  Responses are normally created by the Quixote publisher
    or by the HTTPRequest class (every request must have a response,
    after all).

    Instance attributes:
      content_type : string
        the MIME content type of the response (does not include extra params
        like charset)
      charset : string | None
        the character encoding of the the response.  If none, the 'charset'
        parameter of the Context-Type header will not be included.
      status_code : int
        HTTP response status code (integer between 100 and 599)
      reason_phrase : string
        the reason phrase that accompanies status_code (usually
        set automatically by the set_status() method)
      headers : { string : string }
        most of the headers included with the response; every header set
        by 'set_header()' goes here.  Does not include "Status" or
        "Set-Cookie" headers (unless someone uses set_header() to set
        them, but that would be foolish).
      body : str | Stream
        the response body, None by default.  Note that if the body is not a
        stream then it is already encoded using 'charset'.
      buffered : bool
        if false, response data will be flushed as soon as it is
        written (the default is true).  This is most useful for
        responses that use the Stream() protocol.  Note that whether the
        client actually receives the partial response data is highly
        dependent on the web server
      cookies : { name:string : { attrname : value } }
        collection of cookies to set in this response; it is expected
        that the user-agent will remember the cookies and send them on
        future requests.  The cookie value is stored as the "value"
        attribute.  The other attributes are as specified by RFC 2109.
      cache : int | None
        the number of seconds the response may be cached.  The default
        is 0, meaning don't cache at all.  This variable is used to set
        the HTTP expires and cache-control headers.  If set to None then
        no headers will be added.
      javascript_code : { string : string }
        a collection of snippets of JavaScript code to be included in
        the response.  The collection is built by calling add_javascript(),
        but actually including the code in the HTML document is somebody
        else's problem.
    """

    DEFAULT_CONTENT_TYPE = 'text/html'
    DEFAULT_CHARSET = None # defaults to quixote.DEFAULT_CHARSET


    def __init__(self, status=200, body=None, content_type=None, charset=None):
        """
        Creates a new HTTP response.
        """
        self.content_type = content_type or self.DEFAULT_CONTENT_TYPE
        self.charset = (charset or
                        self.DEFAULT_CHARSET or
                        quixote.DEFAULT_CHARSET)
        self.set_status(status)
        self.headers = {}

        if body is not None:
            self.set_body(body)
        else:
            self.body = None

        self.cookies = {}
        self.cache = 0
        self.buffered = True
        self.javascript_code = None
        self._allow_chunked = False

    def set_content_type(self, content_type, charset=None):
        """(content_type : string, charset : string = None)

        Set the content type of the response to the MIME type specified by
        'content_type'.  If 'charset' is not provided and the content_type is
        text/* then the charset attribute remains unchanged, otherwise the
        charset attribute is set to None and the charset parameter will not
        be included as part of the Content-Type header.
        """
        content_type = content_type.lower()
        if charset is not None or not content_type.startswith('text/'):
            self.charset = charset
        self.content_type = content_type

    def set_charset(self, charset):
        if not charset:
            self.charset = None
        else:
            self.charset = charset.lower()

    def set_status(self, status, reason=None):
        """set_status(status : int, reason : string = None)

        Sets the HTTP status code of the response.  'status' must be an
        integer in the range 100 .. 599.  'reason' must be a string; if
        not supplied, the default reason phrase for 'status' will be
        used.  If 'status' is a non-standard status code, the generic
        reason phrase for its group of status codes will be used; eg.
        if status == 493, the reason for status 400 will be used.
        """
        if not isinstance(status, int):
            raise TypeError("status must be an integer")
        if not (100 <= status <= 599):
            raise ValueError("status must be between 100 and 599")

        self.status_code = status
        if reason is None:
            if status in status_reasons:
                reason = status_reasons[status]
            else:
                # Eg. for generic 4xx failures, use the reason
                # associated with status 400.
                reason = status_reasons[status - (status % 100)]
        else:
            reason = str(reason)

        self.reason_phrase = reason

    def set_header(self, name, value):
        """set_header(name : string, value : string)

        Sets an HTTP return header "name" with value "value", clearing
        the previous value set for the header, if one exists.
        """
        self.headers[name.lower()] = value

    def get_header(self, name, default=None):
        """get_header(name : string, default=None) -> value : string

        Gets an HTTP return header "name".  If none exists then 'default' is
        returned.
        """
        return self.headers.get(name.lower(), default)

    def set_expires(self, seconds=0, minutes=0, hours=0, days=0):
        if seconds is None:
            self.cache = None # don't generate 'Expires' header
        else:
            self.cache = seconds + 60*(minutes + 60*(hours + 24*days))

    def _encode_chunk(self, chunk):
        """(chunk : str) -> bytes
        """
        if isinstance(chunk, str):
            if self.charset is None:
                # iso-8859-1 is the default for the HTTP protocol if charset
                # parameter of content-type header is not provided
                chunk = chunk.encode('iso-8859-1')
            else:
                chunk = chunk.encode(self.charset)
        else:
            # we assume that the str is in the correct encoding or does
            # not contain character data
            pass
        return chunk

    def _compress_body(self, body):
        """(body: bytes) -> bytes
        """
        n = len(body)
        compressed_body = b''.join(self._generate_compressed([body]))
        ratio = float(n) / len(compressed_body)
        #print("gzip original size %d, ratio %.1f" % (n, ratio))
        if ratio > 1.0:
            # only compress if we save space
            self.set_header("Content-Encoding", "gzip")
            return compressed_body
        else:
            return body

    def _generate_compressed(self, body):
        co = zlib.compressobj(6, zlib.DEFLATED, -zlib.MAX_WBITS,
                                  zlib.DEF_MEM_LEVEL, 0)
        crc = zlib.crc32(b'') & 0xffffffff
        n = 0
        yield _GZIP_HEADER
        for chunk in body:
            if not isinstance(chunk, bytes):
                chunk = self._encode_chunk(stringify(chunk))
            crc = zlib.crc32(chunk, crc) & 0xffffffff
            n += len(chunk)
            yield co.compress(chunk)
        crc = struct.pack("<LL", _LOWU32(crc), _LOWU32(n))
        yield co.flush() + crc

    def set_body(self, body, compress=False):
        """(body : any, compress : bool = False)

        Sets the response body equal to the argument 'body'.  If 'compress'
        is true then the body may be compressed.
        """
        if not isinstance(body, Stream):
            if not isinstance(body, bytes):
                body = self._encode_chunk(stringify(body))
            if compress and self.content_type not in _GZIP_EXCLUDE:
                body = self._compress_body(body)
        else:
            if compress and self.content_type not in _GZIP_EXCLUDE:
                self.set_header("Content-Encoding", "gzip")
                body = Stream(self._generate_compressed(body))
        self.body = body

    def expire_cookie(self, name, **attrs):
        """
        Cause an HTTP cookie to be removed from the browser

        The response will include an HTTP header that will remove the cookie
        corresponding to "name" on the client, if one exists.  This is
        accomplished by sending a new cookie with an expiration date
        that has already passed.  Note that some clients require a path
        to be specified - this path must exactly match the path given
        when creating the cookie.  The path can be specified as a keyword
        argument.
        """
        dict = {'max_age': 0, 'expires': 'Thu, 01-Jan-1970 00:00:00 GMT'}
        dict.update(attrs)
        self.set_cookie(name, "deleted", **dict)

    def set_cookie(self, name, value, **attrs):
        """Set an HTTP cookie on the browser.

        The response will include an HTTP header that sets a cookie on
        cookie-enabled browsers with a key "name" and value "value".
        Cookie attributes such as "expires" and "domains" may be
        supplied as keyword arguments; see RFC 2109 for a full list.
        (For the "secure" and httponly attributes, use any true value.)

        This overrides any previous value for this cookie.  Any
        previously-set attributes for the cookie are preserved, unless
        they are explicitly overridden with keyword arguments to this
        call.
        """
        cookies = self.cookies
        if name in cookies:
            cookie = cookies[name]
        else:
            cookie = cookies[name] = {}
        cookie.update(attrs)
        cookie['value'] = value

    def add_javascript(self, code_id, code):
        """Add javascript code to be included in the response.

        code_id is used to ensure that the same piece of code is not
        included twice.  The caller must be careful to avoid
        unintentional code_id and javascript identifier collisions.
        Note that the response object only provides a mechanism for
        collecting code -- actually including it in the HTML document
        that is the response body is somebody else's problem.  (For
        an example, see Form._render_javascript().)
        """
        if self.javascript_code is None:
            self.javascript_code = {code_id: code}
        elif code_id not in self.javascript_code:
            self.javascript_code[code_id] = code

    def redirect(self, location, permanent=False):
        """Cause a redirection without raising an error"""
        if not isinstance(location, str):
            raise TypeError("location must be a string (got %r)" % location)
        # Ensure that location is a full URL
        if location.find('://') == -1:
            raise ValueError("URL must include the server name")
        if permanent:
            status = 301
        else:
            status = 302
        self.set_status(status)
        self.headers['location'] = location
        self.set_content_type('text/plain')
        return "Your browser should have redirected you to %s" % location

    def get_status_code(self):
        return self.status_code

    def get_reason_phrase(self):
        return self.reason_phrase

    def get_content_type(self):
        return self.content_type

    def get_content_length(self):
        if self.body is None:
            return None
        elif isinstance(self.body, Stream):
            return self.body.length
        else:
            return len(self.body)

    def enable_transfer_chunked(self):
        """Allow response to be sent as "Transfer-Encoding: chunked"
        """
        self._allow_chunked = True

    def _gen_cookie_headers(self):
        """_gen_cookie_headers() -> [string]

        Build a list of "Set-Cookie" headers based on all cookies
        set with 'set_cookie()', and return that list.
        """
        cookie_headers = []
        for name, attrs in self.cookies.items():
            value = str(attrs['value'])
            if '"' in value:
                value = value.replace('"', '\\"')
            chunks = ['%s="%s"' % (name, value)]
            for name, val in attrs.items():
                name = name.lower()
                if val is None:
                    continue
                elif name == 'value':
                    continue
                elif name == 'secure' and val:
                    chunks.append("secure")
                elif name == 'httponly' and val:
                    chunks.append("httponly")
                else:
                    name = name.replace('_', '-')
                    chunks.append('%s=%s' % (name, val))
            cookie_headers.append(("Set-Cookie", '; '.join(chunks)))
        return cookie_headers

    def generate_headers(self):
        """generate_headers() -> [(name:string, value:string)]

        Generate a list of headers to be returned as part of the response.
        """
        # Date header
        now = time.time()
        if "date" not in self.headers:
            self.headers['date'] =  formatdate(now, usegmt=True)

        # Cache directives
        if self.cache is None or "expires" in self.headers:
            pass # don't mess with the expires or cache control header
        else:
            # We add both an Expires header and a Cache-Control header
            # with a max-age directive.  The max-age directive takes
            # priority when both Expires and max-age are present (even
            # if Expires is more restrictive, RFC 2616 section 14.9.3).
            if self.cache > 0:
                expire_date = formatdate(now + self.cache, usegmt=True)
                cache_control = "max-age=%d" % self.cache
            else:
                # This is the default case and makes sense for a
                # dynamically generated response that can change on each
                # request.
                #
                # Using the current date is not a good idea since clocks
                # might not be synchronized. Any invalid date is treated
                # as in the past but Microsoft recommends "-1" for
                # Internet Explorer so that's what we use.
                expire_date = "-1"
                # The Expires header is sufficient for HTTP 1.0 but
                # for HTTP 1.1 we must add a must-revalidate directive.
                # Clients and proxies are allowed to ignore Expires in
                # certain cases and use stale pages (RFC 2616 sections
                # 13.1.5 and 14.9.4).
                cache_control = "max-age=0, no-cache"
            if ("expires" not in self.headers and
                    "cache-control" not in self.headers):
                # If either of these headers are set then don't add
                # any of them. We assume the programmer knows what he
                # is doing in that case.
                self.headers['expires'] = expire_date
                self.headers['cache-control'] = cache_control

        # Content-type
        if "content-type" not in self.headers:
            if self.charset is not None:
                value = '%s; charset=%s' % (self.content_type, self.charset)
            else:
                value = '%s' % self.content_type
            self.headers['content-type'] = value

        # Content-Length
        if "content-length" not in self.headers:
            length = self.get_content_length()
            if length is not None:
                self.headers['content-length'] = str(length)
            elif self._allow_chunked:
                # No content-length and chunked encoding possible,
                # use it.
                self.headers['transfer-encoding'] = 'chunked'
            else:
                self.headers['connection'] = 'close'

        headers = []
        for name, value in self.headers.items():
            headers.append((name.title(), value))
        if self.cookies:
            # All the "Set-Cookie" headers.
            headers.extend(self._gen_cookie_headers())
        return headers

    def _generate_encoded_body(self):
        """Return a sequence of body chunks, encoded using 'charset'.
        """
        if self.body is None:
            pass
        elif isinstance(self.body, Stream):
            for chunk in self.body:
                if not isinstance(chunk, bytes):
                    chunk = self._encode_chunk(chunk)
                yield chunk
        else:
            yield self.body # already encoded

    def _generate_transfer_chunked(self, stream):
        """Convert a sequence of encoded body data into the format
        # expected by "Transfer-Encoding: chunked".
        """
        # Each chunk is as follows:
        #    <length of data hex><CRLF>
        #    <data><CRLF>
        #    <CRLF>
        # The stream is terminated by a zero length chunk.
        for chunk in stream:
            if chunk:
                yield b''.join([('%x\r\n' % len(chunk)).encode(), chunk, b'\r\n'])
        yield b'0\r\n\r\n'

    def generate_body_chunks(self):
        stream = self._generate_encoded_body()
        if self.headers.get('transfer-encoding') == 'chunked':
            return self._generate_transfer_chunked(stream)
        else:
            return stream

    def write(self, output, include_status=True, include_body=True):
        """(output:file, include_status:bool=True, include_body:bool=True)

        Write the HTTP response headers and, by default, body to 'output'.
        This is not a complete HTTP response, as it doesn't start with a
        response status line as specified by RFC 2616.  By default, it
        does start with a "Status" header as described by the CGI spec.
        It is expected that this response is parsed by the web server and
        turned into a complete HTTP response. If include_body is False,
        only the headers are written to 'output'. This is used to support
        HTTP HEAD requests.
        """
        flush_output = not self.buffered and hasattr(output, 'flush')
        if include_status:
            # "Status" header must come first.
            s = 'Status: %03d %s\r\n' % (self.status_code, self.reason_phrase)
            output.write(s.encode('utf-8'))

        for name, value in self.generate_headers():
            s = "%s: %s\r\n" % (name, value)
            output.write(s.encode('utf-8'))
        output.write(b"\r\n")
        if flush_output:
            output.flush()
        if not include_body:
            return
        for chunk in self.generate_body_chunks():
            output.write(chunk)
            if flush_output:
                output.flush()
        if flush_output:
            output.flush()


class Stream:
    """
    A wrapper around response data that can be streamed.  The 'iterable'
    argument must support the iteration protocol.  Items returned by 'next()'
    must be strings.  Beware that exceptions raised while writing the stream
    will not be handled gracefully.

    Instance attributes:
      iterable : any
        an object that supports the iteration protocol.  The items produced
        by the stream must be strings.
      length: int | None
        the number of bytes that will be produced by the stream, None
        if it is not known.  Used to set the Content-Length header.
    """
    def __init__(self, iterable, length=None):
        self.iterable = iterable
        self.length = length

    def __iter__(self):
        return iter(self.iterable)
