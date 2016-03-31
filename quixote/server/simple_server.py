#!/usr/bin/env python3
"""A simple, single threaded, synchronous HTTP server.
"""
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer
import urllib.request, urllib.parse, urllib.error
import quixote
from quixote import get_publisher
from quixote.util import import_object

class HTTPRequestHandler(BaseHTTPRequestHandler):

    required_cgi_environment = {}

    protocol_version = 'HTTP/1.1'

    def get_cgi_env(self, method):
        env = dict(
            SERVER_SOFTWARE="Quixote/%s" % quixote.__version__,
            SERVER_NAME=self.server.server_name,
            GATEWAY_INTERFACE='CGI/1.1',
            SERVER_PROTOCOL=self.protocol_version,
            SERVER_PORT=str(self.server.server_port),
            REQUEST_METHOD=method,
            REMOTE_ADDR=self.client_address[0],
            SCRIPT_NAME='')
        if '?' in self.path:
            env['PATH_INFO'], env['QUERY_STRING'] = self.path.split('?', 1)
        else:
            env['PATH_INFO'] = self.path
        env['PATH_INFO'] = urllib.parse.unquote(env['PATH_INFO'])
        env['CONTENT_TYPE'] = self.headers.get('content-type')
        env['CONTENT_LENGTH'] = self.headers.get('content-length') or "0"
        for name, value in self.headers.items():
            header_name = 'HTTP_' + name.upper().replace('-', '_')
            env[header_name] = value
        accept = []
        for line in self.headers.getallmatchingheaders('accept'):
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

    def process(self, env, include_body=True):
        response = get_publisher().process(self.rfile, env)
        if self.protocol_version == 'HTTP/1.1':
            # single threaded server, persistent connections will block others
            response.set_header('connection', 'close')
        try:
            self.send_response(response.get_status_code(), response.get_reason_phrase())
            self.flush_headers()
            response.write(self.wfile, include_status=False, include_body=include_body)
        except IOError as err:
            print("IOError while sending response ignored: %s" % err)

    def do_POST(self):
        return self.process(self.get_cgi_env('POST'))

    def do_GET(self):
        return self.process(self.get_cgi_env('GET'))

    def do_HEAD(self):
        return self.process(self.get_cgi_env('HEAD'), include_body=False)

    def send_response(self, code, message=None):
        """
        Copied, with regret, from BaseHTTPRequestHandler, except that the line
        that adds the 'Date' header is removed to avoid duplicating the one
        that Quixote adds and the log_request() call has been removed.
        """
        self.send_response_only(code, message)
        self.send_header('Server', self.version_string())

def run(create_publisher, host='', port=80, https=False):
    """Runs a simple, single threaded, synchronous HTTP server that
    publishes a Quixote application.
    """
    if https:
        HTTPRequestHandler.required_cgi_environment['HTTPS'] = 'on'
    httpd = HTTPServer((host, port), HTTPRequestHandler)
    def handle_error(request, client_address):
        HTTPServer.handle_error(httpd, request, client_address)
        if sys.exc_info()[0] is SystemExit:
            raise
    httpd.handle_error = handle_error
    publisher = create_publisher()
    if publisher.logger.access_log is None:
        publisher.logger.access_log = sys.stdout
    try:
        httpd.serve_forever()
    finally:
        httpd.server_close()

if __name__ == '__main__':
    from quixote.server.util import get_server_parser
    parser = get_server_parser(run.__doc__)
    parser.add_option(
        '--https', dest="https", default=False, action="store_true",
        help=("Force the scheme for all requests to be https.  "
              "Not that this is for running the simple server "
              "through a proxy or tunnel that provides real SSL "
              "support.  The simple server itself does not. "))
    (options, args) = parser.parse_args()
    run(import_object(options.factory), host=options.host, port=options.port,
        https=options.https)
