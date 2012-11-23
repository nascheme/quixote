#!/usr/bin/env python
"""An HTTP server for Twisted that publishes a Quixote application.
"""

import urllib
from twisted.web import http, server
from twisted.python import threadable
from twisted.internet import reactor


class QuixoteFactory(http.HTTPFactory):
    def __init__(self, publisher):
        self.publisher = publisher
        http.HTTPFactory.__init__(self, None)

    def buildProtocol(self, addr):
        protocol = http.HTTPFactory.buildProtocol(self, addr)
        protocol.requestFactory = QuixoteRequest
        return protocol


class QuixoteRequest(server.Request):
    def process(self):
        environ = self.create_environment()
        # this seek is important, it doesn't work without it (it doesn't
        # matter for GETs, but POSTs will not work properly without it.)
        self.content.seek(0, 0)
        qxresponse = self.channel.factory.publisher.process(self.content,
                                                            environ)
        self.setResponseCode(qxresponse.status_code)
        for name, value in qxresponse.generate_headers():
            if name != 'Set-Cookie':
                self.setHeader(name, value)
        # Cookies get special treatment since it seems Twisted cannot handle
        # multiple Set-Cookie headers.
        for name, attrs in qxresponse.cookies.items():
            attrs = attrs.copy()
            value = attrs.pop('value')
            self.addCookie(name, value, **attrs)
        QuixoteProducer(qxresponse, self)

    def create_environment(self):
        """
        Borrowed heavily from twisted.web.twcgi
        """
        # Twisted doesn't decode the path for us, so let's do it here.
        if '%' in self.path:
            self.path = urllib.unquote(self.path)

        serverName = self.getRequestHostname().split(':')[0]
        env = {"SERVER_SOFTWARE":   server.version,
               "SERVER_NAME":       serverName,
               "GATEWAY_INTERFACE": "CGI/1.1",
               "SERVER_PROTOCOL":   self.clientproto,
               "SERVER_PORT":       str(self.getHost().port),
               "REQUEST_METHOD":    self.method,
               "SCRIPT_NAME":       '',
               "SCRIPT_FILENAME":   '',
               "REQUEST_URI":       self.uri,
               "HTTPS":             (self.isSecure() and 'on') or 'off',
               'SERVER_PROTOCOL':   'HTTP/1.1',
        }

        for env_var, header in [('ACCEPT_ENCODING', 'Accept-encoding'),
                                ('CONTENT_TYPE', 'Content-type'),
                                ('HTTP_COOKIE', 'Cookie'),
                                ('HTTP_REFERER', 'Referer'),
                                ('HTTP_USER_AGENT', 'User-agent')]:
            value = self.getHeader(header)
            if value is not None:
                env[env_var] = value

        client = self.getClient()
        if client is not None:
            env['REMOTE_HOST'] = client
        ip = self.getClientIP()
        if ip is not None:
            env['REMOTE_ADDR'] = ip
        remote_port = self.transport.getPeer().port
        env['REMOTE_PORT'] = remote_port
        env["PATH_INFO"] = self.path

        qindex = self.uri.find('?')
        if qindex != -1:
            env['QUERY_STRING'] = self.uri[qindex+1:]
        else:
            env['QUERY_STRING'] = ''

        # Propogate HTTP headers
        for title, header in self.getAllHeaders().items():
            envname = title.replace('-', '_').upper()
            if title not in ('content-type', 'content-length'):
                envname = "HTTP_" + envname
            env[envname] = header

        return env


class QuixoteProducer:
    """
    Produce the Quixote response for twisted.
    """
    def __init__(self, qxresponse, request):
        self.request = request
        self.size = qxresponse.get_content_length()
        self.stream = qxresponse.generate_body_chunks()
        request.registerProducer(self, 0)

    def resumeProducing(self):
        if self.request:
            try:
                chunk = self.stream.next()
            except StopIteration:
                self.request.unregisterProducer()
                self.request.finish()
                self.request = None
            else:
                self.request.write(chunk)

    def pauseProducing(self):
        pass

    def stopProducing(self):
        self.request = None

    synchronized = ['resumeProducing', 'stopProducing']

threadable.synchronize(QuixoteProducer)


def run(create_publisher, host='', port=80):
    """Runs a Twisted HTTP server server that publishes a Quixote
    application."""
    publisher = create_publisher()
    factory = QuixoteFactory(publisher)
    reactor.listenTCP(port, factory, interface=host)
    reactor.run()


if __name__ == '__main__':
    from quixote.server.util import main
    main(run)
