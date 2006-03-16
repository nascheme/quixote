#!/usr/bin/env python
"""Server for Quixote applications that use FastCGI.  It should work
for CGI too but the cgi_server module is preferred as it is more
portable.
"""

from quixote.server import _fcgi

def run(create_publisher):
    publisher = create_publisher()
    while _fcgi.isFCGI():
        f = _fcgi.FCGI()
        response = publisher.process(f.inp, f.env)
        try:
            response.write(f.out)
        except IOError, err:
            publisher.log("IOError while sending response ignored: %s" % err)
        f.Finish()


if __name__ == '__main__':
    from quixote.demo import create_publisher
    run(create_publisher)
