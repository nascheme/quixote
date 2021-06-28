#!/usr/bin/env python3
"""A simple, multi-threaded HTTP server.  The application processing occurs in
a single back-end thread.  Multiple threads are used for communicating with
HTTP clients.
"""
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
from socketserver import ThreadingMixIn
from quixote import get_publisher
from quixote.http_request import HTTPRequest
from quixote.server import simple_server


class ThreadingHTTPServer(
    ThreadingMixIn, simple_server.SockInheritHTTPServer
):
    pass


def _buffer_request_body(rfile, env):
    """Read the HTTP request body into a temporary file.  Return an
    open file object that points to the start of the file.
    """
    length = env.get('HTTP_CONTENT_LENGTH') or 0
    try:
        length = int(length)
    except ValueError:
        length = 0
    body = tempfile.SpooledTemporaryFile()
    remaining = length
    while remaining > 0:
        s = rfile.read(min(remaining, 10000))
        if not s:
            break
        body.write(s)
        remaining -= len(s)
    body.seek(0)
    return body


class HTTPRequestHandler(simple_server.HTTPRequestHandler):
    def process(self, env, include_body=True):
        """Process a single request, in front-end HTTP server thread."""
        request_body = _buffer_request_body(self.rfile, env)
        try:
            # submit work to back-end executor
            f = _PROCESSOR.submit(_process, request_body, env, include_body)
            # wait for result from back-end
            status, reason, response_body = f.result()
        finally:
            request_body.close()
        try:
            self.send_response(status, reason)
            self.flush_headers()
            while True:
                buf = response_body.read(20000)
                if not buf:
                    break
                self.wfile.write(buf)
            response_body.close()
        except IOError as err:
            print("IOError while sending response ignored: %s" % err)


def _process(rfile, env, include_body):
    """Process a single request, in background Quixote thread."""
    request = HTTPRequest(rfile, env, seekable=True)
    response = get_publisher().process_request(request)
    status, reason = response.get_status_code(), response.get_reason_phrase()
    # write response body to temporary file, this ensures that write() runs in
    # the correct thread and we are not blocked by slow clients.
    body = tempfile.SpooledTemporaryFile()
    response.write(body, include_status=False, include_body=include_body)
    body.seek(0)
    return (status, reason, body)


def run(create_publisher, host='', port=80, https=False):
    """Runs a simple, multi-threaded, HTTP server that publishes a Quixote
    application.
    """
    global _PROCESSOR
    if https:
        HTTPRequestHandler.required_cgi_environment['HTTPS'] = 'on'
    httpd = ThreadingHTTPServer((host, port), HTTPRequestHandler)

    def handle_error(request, client_address):
        ThreadingHTTPServer.handle_error(httpd, request, client_address)
        if sys.exc_info()[0] is SystemExit:
            raise

    httpd.handle_error = handle_error

    with ThreadPoolExecutor(
        max_workers=1,
        initializer=create_publisher,
    ) as _PROCESSOR:
        try:
            httpd.serve_forever()
        finally:
            httpd.server_close()


def main(args=None):
    simple_server.main(args=args, _run=run)


if __name__ == '__main__':
    main()
