#!/usr/bin/env python
"""An HTTP handler for Medusa that publishes a Quixote application.
"""

import asyncore, rfc822, socket, urllib
from StringIO import StringIO
from medusa import http_server, xmlrpc_handler
import quixote


class StreamProducer:
    def __init__(self, chunks):
        self.chunks = chunks # a generator

    def more(self):
        try:
            return self.chunks.next()
        except StopIteration:
            return ''


class QuixoteHandler:
    def __init__(self, publisher, server):
        self.publisher = publisher
        self.server = server

    def match(self, request):
        # Always match, since this is the only handler there is.
        return True

    def handle_request(self, request):
        msg = rfc822.Message(StringIO('\n'.join(request.header)))
        length = int(msg.get('Content-Length', '0'))
        if length:
            request.collector = xmlrpc_handler.collector(self, request)
        else:
            self.continue_request('', request)

    def continue_request(self, data, request):
        msg = rfc822.Message(StringIO('\n'.join(request.header)))
        remote_addr, remote_port = request.channel.addr
        if '#' in request.uri:
            # MSIE is buggy and sometimes includes fragments in URLs
            [request.uri, fragment] = request.uri.split('#', 1)
        if '?' in request.uri:
            [path, query_string] = request.uri.split('?', 1)
        else:
            path = request.uri
            query_string = ''

        path = urllib.unquote(path)
        server_port = str(self.server.port)
        http_host = msg.get("Host")
        if http_host:
            if ":" in http_host:
                server_name, server_port = http_host.split(":", 1)
            else:
                server_name = http_host
        else:
            server_name = (self.server.ip or
                           socket.gethostbyaddr(socket.gethostname())[0])

        environ = {'REQUEST_METHOD': request.command,
                   'ACCEPT_ENCODING': msg.get('Accept-encoding', ''),
                   'CONTENT_TYPE': msg.get('Content-type', ''),
                   'CONTENT_LENGTH': len(data),
                   "GATEWAY_INTERFACE": "CGI/1.1",
                   'PATH_INFO': path,
                   'QUERY_STRING': query_string,
                   'REMOTE_ADDR': remote_addr,
                   'REMOTE_PORT': str(remote_port),
                   'REQUEST_URI': request.uri,
                   'SCRIPT_NAME': '',
                   "SCRIPT_FILENAME": '',
                   'SERVER_NAME': server_name,
                   'SERVER_PORT': server_port,
                   'SERVER_PROTOCOL': 'HTTP/1.1',
                   'SERVER_SOFTWARE': 'Quixote/%s' % quixote.__version__,
                   }
        for title, header in msg.items():
            envname = 'HTTP_' + title.replace('-', '_').upper()
            environ[envname] = header

        stdin = StringIO(data)
        qresponse = self.publisher.process(stdin, environ)

        # Copy headers from Quixote's HTTP response
        for name, value in qresponse.generate_headers():
            # XXX Medusa's HTTP request is buggy, and only allows unique
            # headers.
            request[name] = value

        request.response(qresponse.status_code)
        request.push(StreamProducer(qresponse.generate_body_chunks()))
        request.done()


def run(create_publisher, host='', port=80):
    """Runs a Medusa HTTP server that publishes a Quixote
    application.
    """
    server = http_server.http_server(host, port)
    publisher = create_publisher()
    handler = QuixoteHandler(publisher, server)
    server.install_handler(handler)
    asyncore.loop()


if __name__ == '__main__':
    from quixote.server.util import main
    main(run)
