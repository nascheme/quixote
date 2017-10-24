"""An example of a WSGI server module.

This is not so useful in practice since using simple_server provides the
same functionality with less complication.  However, this module might
be useful as an example as to how to run a Quixote application under
WSGI.
"""
import sys
from wsgiref.simple_server import WSGIServer, ServerHandler, \
    WSGIRequestHandler
from quixote.wsgi import QWIP
from quixote.util import import_object

# Need to override base class handle(), set multithread=False
class RequestHandler(WSGIRequestHandler):
    def handle(self):
        """Handle a single HTTP request"""

        self.raw_requestline = self.rfile.readline(65537)
        if len(self.raw_requestline) > 65536:
            self.requestline = ''
            self.request_version = ''
            self.command = ''
            self.send_error(414)
            return

        if not self.parse_request(): # An error code has been sent, just exit
            return

        handler = ServerHandler(
            self.rfile, self.wfile, self.get_stderr(), self.get_environ(),
            multithread=False, multiprocess=False)

        handler.request_handler = self      # backpointer for logging
        handler.run(self.server.get_app())


def run(create_publisher, host='', port=80, handler_class=RequestHandler):
    """Runs a Quixote application using the simple server from wsgiref.
    """
    publisher = create_publisher()
    app = QWIP(publisher)
    server = WSGIServer((host, port), handler_class)
    server.set_app(app)
    try:
        server.serve_forever()
    finally:
        server.server_close()


def main(args=None):
    from quixote.server.util import get_server_parser
    if args is None:
        args = sys.argv[1:]
    parser = get_server_parser(run.__doc__)
    (options, args) = parser.parse_args(args=args)
    run(import_object(options.factory), host=options.host, port=options.port)


if __name__ == '__main__':
    main()
