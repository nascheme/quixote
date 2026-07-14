#!/usr/bin/env python3
"""A simple, single threaded, synchronous HTTP server."""

from __future__ import annotations

import socket
import sys
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable, Sequence
from http.server import BaseHTTPRequestHandler, HTTPServer
from socketserver import BaseRequestHandler, BaseServer
from typing import Any, Protocol, cast

import quixote
from quixote import get_publisher
from quixote.http_request import Environ
from quixote.publish import Publisher
from quixote.util import import_object

try:
    from scgi.systemd_socket import get_systemd_socket
except ImportError:

    def get_systemd_socket() -> socket.socket | None:
        return None


CreatePublisher = Callable[[], Publisher]


class _SimpleRun(Protocol):
    def __call__(
        self,
        create_publisher: CreatePublisher,
        *,
        host: str = '',
        port: int = 80,
        https: bool = False,
    ) -> None: ...


class SockInheritHTTPServer(HTTPServer):
    def __init__(
        self,
        address_info: tuple[str, int],
        handler: type[BaseRequestHandler],
        bind_and_activate: bool = True,
    ) -> None:
        # This is ugly.  We have to re-implement HTTPServer.__init__
        # and server_bind().  We want to get the inherited socket if
        # available.  If we inherit then we need to skip the bind() call.
        BaseServer.__init__(self, address_info, handler)
        sock = get_systemd_socket()
        if sock is not None:
            print('Using inherited socket %s' % (sock.getsockname(),))
            self._skip_bind = True
        else:
            sock = socket.socket(self.address_family, self.socket_type)
            self._skip_bind = False
        self.socket = sock
        if bind_and_activate:
            try:
                self.server_bind()
                self.server_activate()
            except BaseException:
                self.server_close()
                raise

    def server_bind(self) -> None:
        if not self._skip_bind:
            HTTPServer.server_bind(self)
        else:
            self.server_address = self.socket.getsockname()
            host, port = self.socket.getsockname()[:2]
            self.server_name = socket.getfqdn(host)
            self.server_port = port


class HTTPRequestHandler(BaseHTTPRequestHandler):
    required_cgi_environment: dict[str, str] = {}

    protocol_version = 'HTTP/1.1'

    def get_cgi_env(self, method: str) -> Environ:
        server = cast(SockInheritHTTPServer, self.server)
        env = dict(
            SERVER_SOFTWARE="Quixote/%s" % quixote.__version__,
            SERVER_NAME=server.server_name,
            GATEWAY_INTERFACE='CGI/1.1',
            SERVER_PROTOCOL=self.protocol_version,
            SERVER_PORT=str(server.server_port),
            REQUEST_METHOD=method,
            REMOTE_ADDR=self.client_address[0],
            SCRIPT_NAME='',
        )
        if '?' in self.path:
            env['PATH_INFO'], env['QUERY_STRING'] = self.path.split('?', 1)
        else:
            env['PATH_INFO'] = self.path
        env['PATH_INFO'] = urllib.parse.unquote(env['PATH_INFO'])
        env['CONTENT_TYPE'] = self.headers.get('content-type') or ''
        env['CONTENT_LENGTH'] = self.headers.get('content-length') or "0"
        for name, value in self.headers.items():
            header_name = 'HTTP_' + name.upper().replace('-', '_')
            env[header_name] = value
        accept = []
        for line in cast(Any, self.headers).getallmatchingheaders('accept'):
            if line[:1] in "\t\n\r ":
                accept.append(line.strip())
            else:
                accept = accept + line[7:].split(',')
        env['HTTP_ACCEPT'] = ','.join(accept)
        co = [c for c in self.headers.get_all('cookie') or [] if c]
        if co:
            env['HTTP_COOKIE'] = ', '.join(co)
        env.update(self.required_cgi_environment)
        return env

    def process(self, env: Environ, include_body: bool = True) -> None:
        response = get_publisher().process(cast(Any, self.rfile), env)
        if self.protocol_version == 'HTTP/1.1':
            # single threaded server, persistent connections will block others
            response.set_header('connection', 'close')
        try:
            self.send_response(
                response.get_status_code(), response.get_reason_phrase()
            )
            self.flush_headers()
            response.write(
                cast(Any, self.wfile),
                include_status=False,
                include_body=include_body,
            )
        except IOError as err:
            print("IOError while sending response ignored: %s" % err)

    def do_POST(self) -> None:
        return self.process(self.get_cgi_env('POST'))

    def do_GET(self) -> None:
        return self.process(self.get_cgi_env('GET'))

    def do_HEAD(self) -> None:
        return self.process(self.get_cgi_env('HEAD'), include_body=False)

    def do_OPTIONS(self) -> None:
        return self.process(self.get_cgi_env('OPTIONS'), include_body=False)

    def send_response(self, code: int, message: str | None = None) -> None:
        """
        Copied, with regret, from BaseHTTPRequestHandler, except that the line
        that adds the 'Date' header is removed to avoid duplicating the one
        that Quixote adds and the log_request() call has been removed.
        """
        self.send_response_only(code, message)
        self.send_header('Server', self.version_string())


def run(
    create_publisher: CreatePublisher,
    host: str = '',
    port: int = 80,
    https: bool = False,
) -> None:
    """Runs a simple, single threaded, synchronous HTTP server that
    publishes a Quixote application.
    """
    if https:
        HTTPRequestHandler.required_cgi_environment['HTTPS'] = 'on'
    httpd = SockInheritHTTPServer((host, port), HTTPRequestHandler)

    def handle_error(request: object, client_address: object) -> None:
        HTTPServer.handle_error(
            httpd, cast(Any, request), cast(Any, client_address)
        )
        if sys.exc_info()[0] is SystemExit:
            raise

    httpd.handle_error = handle_error
    publisher = create_publisher()
    logger = cast(Any, publisher.logger)
    if logger.access_log is None:
        logger.access_log = sys.stdout
    try:
        httpd.serve_forever()
    finally:
        httpd.server_close()


def main(args: Sequence[str] | None = None, _run: _SimpleRun = run) -> None:
    from quixote.server.util import get_server_parser

    if args is None:
        args = sys.argv[1:]
    parser = get_server_parser(run.__doc__)
    parser.add_option(
        '--https',
        dest="https",
        default=False,
        action="store_true",
        help=(
            "Force the scheme for all requests to be https.  "
            "Not that this is for running the simple server "
            "through a proxy or tunnel that provides real SSL "
            "support.  The simple server itself does not. "
        ),
    )
    (options, args) = parser.parse_args(args=args)
    _run(
        cast(CreatePublisher, import_object(options.factory)),
        host=options.host,
        port=options.port,
        https=options.https,
    )


if __name__ == '__main__':
    main()
