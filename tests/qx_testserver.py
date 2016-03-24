"""
A simple test server for testing Quixote functionality.
"""

import os
from quixote.publish import Publisher
from quixote.directory import Directory

def create_publisher():
    "Create & return a test publisher entry"
    p = Publisher(TestServer())
    p.is_thread_safe = True

    return p

class TestServer(Directory):
    _q_exports = ['', 'exit']

    def _q_index(self):
        return "hello, world"

    def exit(self):
        raise SystemExit
    
if __name__ == '__main__':
    from quixote.server.simple_server import run
    port = int(os.environ.get('QX_TEST_PORT', '8080'))
    print('starting qx_testserver on port %d.' % (port,))
    try:
        run(create_publisher, port=port)
    except KeyboardInterrupt:
        pass
