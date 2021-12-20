import sys
import twill
import quixote
from qx_testserver import create_publisher


class TestWSGI:
    def setup(self):
        wsgi_app = None

        x = sys.stdout  # Quixote mangles sys.stdout; save.
        try:
            publisher = create_publisher()  # noqa: F841
            wsgi_app = quixote.get_wsgi_app()
        finally:
            sys.stdout = x  # restore.

        twill.add_wsgi_intercept(
            'localhost', 80, lambda: wsgi_app, '/qx_test'
        )

    def teardown(self):
        twill.remove_wsgi_intercept('localhost', 80)

        quixote.cleanup()

    def test(self):
        twill.commands.go('http://localhost:80/qx_test/')
        twill.commands.find('hello, world')
