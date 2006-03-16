#!/usr/bin/env python
"""$URL: svn+ssh://svn.mems-exchange.org/repos/trunk/quixote/server/fastcgi_server.py $
$Id: fastcgi_server.py 27684 2005-11-10 15:25:17Z dbinger $

Server for Quixote applications that use FastCGI.  It should work
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
