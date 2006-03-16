"""Miscellaneous utility functions shared by servers.
"""

from optparse import OptionParser
from quixote.util import import_object

def get_server_parser(doc):
    parser = OptionParser()
    parser.set_description(doc)
    default_host = 'localhost'
    parser.add_option(
        '--host', dest="host", default=default_host, type="string",
        help="Host interface to listen on. (default=%s)" % default_host)
    default_port = 8080
    parser.add_option(
        '--port', dest="port", default=default_port, type="int",
        help="Port to listen on. (default=%s)" % default_port)
    default_factory = 'quixote.demo.create_publisher'
    parser.add_option(
        '--factory', dest="factory",
        default=default_factory,
        help="Path to factory function to create the site Publisher. "
             "(default=%s)" % default_factory)
    return parser

def main(run):
    parser = get_server_parser(run.__doc__)
    (options, args) = parser.parse_args()
    run(import_object(options.factory), host=options.host, port=options.port)
