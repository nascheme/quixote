"""
This needs testing.

mod_python configuration
------------------------

mod_python is an Apache module for embedding a Python interpreter into
the Apache server.  To use mod_python as the interface layer between
Apache and Quixote, add something like this to your httpd.conf::

    LoadModule python_module /usr/lib/apache/1.3/mod_python.so
    <LocationMatch "^/qdemo(/|$)">
        SetHandler python-program
        PythonHandler quixote.server.mod_python_handler
        PythonOption quixote-publisher-factory quixote.demo.create_publisher
        PythonInterpreter quixote.demo
        PythonDebug On
    </LocationMatch>

This will attach URLs starting with ``/qdemo`` to the Quixote demo.
When you use mod_python, there's no need for rewrite rules (because of
the pattern in the ``LocationMatch`` directive), and no need for a
driver script.  

mod_python support was contributed to Quixote (1) by Erno Kuusela
<erno@iki.fi> and the Quixote 2 port comes from Clint.
"""

import sys
from mod_python import apache
from quixote.publish import Publisher
from quixote.util import import_object

class ErrorLog:
    def __init__(self, publisher):
        self.publisher = publisher

    def write(self, msg):
        self.publisher.log(msg)

    def close(self):
        pass

class ModPythonPublisher(Publisher):
    def __init__(self, package, **kwargs):
        Publisher.__init__(self, package, **kwargs)
        # may be overwritten
        self.logger.error_log = self.__error_log = ErrorLog(self)
        self.__apache_request = None

    def log(self, msg):
        if self.logger.error_log is self.__error_log:
            try:
                self.__apache_request.log_error(msg)
            except AttributeError:
                apache.log_error(msg)
        else:
            Publisher.log(self, msg)

    def publish_modpython(self, req):
        """publish_modpython() -> None

        Entry point from mod_python.
        """
        self.__apache_request = req
        try:
            self.publish(apache.CGIStdin(req),
                         apache.CGIStdout(req),
                         sys.stderr,
                         apache.build_cgi_env(req))

            return apache.OK
        finally:
            self.__apache_request = None

name2publisher = {}

def run(publisher, req):
    response = publisher.process(apache.CGIStdin(req),
                                 apache.build_cgi_env(req))
    try:
        response.write(apache.CGIStdout(req))
    except IOError, err:
        publisher.log("IOError while  sending response ignored: %s" % err)
    return apache.OK

def handler(req):
    opts = req.get_options()
    try:
        factory = opts['quixote-publisher-factory']
    except KeyError:
        apache.log_error('quixote-publisher-factory setting required')
        return apache.HTTP_INTERNAL_SERVER_ERROR
    pub = name2publisher.get(factory)
    if pub is None:
        factory_fcn = import_object(factory)
        pub = factory_fcn()
        name2publisher[factory] = pub
    return run(pub, req)

