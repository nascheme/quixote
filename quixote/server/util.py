"""Miscellaneous utility functions shared by servers.
"""

from optparse import OptionParser
from quixote.util import import_object


class Parser(OptionParser):
    def parse_args(self, *args, **kwargs):
        options, values = OptionParser.parse_args(self, *args, **kwargs)
        if options.factory and '.' not in options.factory:
            # make factory include package name as well
            options.factory = options.app + '.' + options.factory
        return options, values


def get_server_parser(doc):
    parser = Parser()
    parser.set_description(doc)
    default_host = 'localhost'
    parser.add_option(
        '--host',
        dest="host",
        default=default_host,
        type="string",
        help="Host interface to listen on. (default=%s)" % default_host,
    )
    default_port = 8080
    parser.add_option(
        '--port',
        dest="port",
        default=default_port,
        type="int",
        help="Port to listen on. (default=%s)" % default_port,
    )
    default_factory = 'create_publisher'
    parser.add_option(
        '--factory',
        dest="factory",
        default=default_factory,
        help="Path to factory function to create the site Publisher. "
        "If it does not contain a dot, it is relative to app package. "
        "(default=%s)" % default_factory,
    )
    default_app = 'quixote.demo'
    parser.add_option(
        '--app',
        dest="app",
        default=default_app,
        help="Name of package that contains Quixote application. "
        "(default=%s)" % default_app,
    )
    return parser


def main(run):
    parser = get_server_parser(run.__doc__)
    (options, args) = parser.parse_args()
    run(import_object(options.factory), host=options.host, port=options.port)
