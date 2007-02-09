#!/usr/bin/env python
"""A SCGI server that uses Quixote to publish dynamic content.
"""

from scgi import scgi_server

class QuixoteHandler(scgi_server.SCGIHandler):
    def __init__(self, parent_fd, create_publisher, script_name=None):
        scgi_server.SCGIHandler.__init__(self, parent_fd)
        self.publisher = create_publisher()
        self.script_name = script_name

    def handle_connection(self, conn):
        input = conn.makefile("r")
        output = conn.makefile("w")
        env = self.read_env(input)

        if self.script_name is not None:
            # mod_scgi doesn't know SCRIPT_NAME :-(
            prefix = self.script_name
            path = env['SCRIPT_NAME']
            assert path[:len(prefix)] == prefix, (
                "path %r doesn't start with script_name %r" % (path, prefix))
            env['SCRIPT_NAME'] = prefix
            env['PATH_INFO'] = path[len(prefix):] + env.get('PATH_INFO', '')

        response = self.publisher.process(input, env)
        try:
            response.write(output)
            input.close()
            output.close()
            conn.close()
        except IOError, err:
            self.publisher.log("IOError while sending response "
                               "ignored: %s" % err)


def run(create_publisher, host='localhost', port=3000, script_name=None,
        max_children=5):
    def create_handler(parent_fd):
        return QuixoteHandler(parent_fd, create_publisher, script_name)
    s = scgi_server.SCGIServer(create_handler, host=host, port=port,
                               max_children=max_children)
    s.serve()


def main():
    from optparse import OptionParser
    from quixote.util import import_object
    parser = OptionParser()
    parser.set_description(run.__doc__)
    default_host = 'localhost'
    parser.add_option(
        '--host', dest="host", default=default_host, type="string",
        help="Host interface to listen on. (default=%s)" % default_host)
    default_port = 3000
    parser.add_option(
        '--port', dest="port", default=default_port, type="int",
        help="Port to listen on. (default=%s)" % default_port)
    default_maxchild = 5
    parser.add_option(
        '--max-children', dest="maxchild", default=default_maxchild,
        type="string",
        help="Maximum number of children to spawn. (default=%s)" %
            default_maxchild)
    parser.add_option(
        '--script-name', dest="script_name", default=None, type="string",
        help="Value of SCRIPT_NAME (only needed if using mod_scgi)")
    default_factory = 'quixote.demo.create_publisher'
    parser.add_option(
        '--factory', dest="factory",
        default=default_factory,
        help="Path to factory function to create the site Publisher. "
             "(default=%s)" % default_factory)
    (options, args) = parser.parse_args()
    run(import_object(options.factory), host=options.host, port=options.port,
        script_name=options.script_name, max_children=options.maxchild)

if __name__ == '__main__':
    main()
