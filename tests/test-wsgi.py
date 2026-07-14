import sys

import twill
from qx_testserver import create_publisher

import quixote


class TestWSGI:
    def setup(self) -> None:
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

    def teardown(self) -> None:
        twill.remove_wsgi_intercept('localhost', 80)

        quixote.cleanup()

    def test(self) -> None:
        twill.commands.go('http://localhost:80/qx_test/')
        twill.commands.find('hello, world')
