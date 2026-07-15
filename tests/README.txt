The automated test suite runs under pytest and lives beside the code it
covers, under quixote/ (e.g. quixote/test/, quixote/html/test/,
quixote/ptl/test/).  Run it from the top-level Quixote directory with:

   uv run pytest -q

This directory holds manual helpers, not automated tests:

   qx_testserver.py    a tiny Publisher/Directory serving "hello, world";
                       run it directly to start a live server
                       (python tests/qx_testserver.py, port QX_TEST_PORT).

   serve-via-wsgi.py   serve qx_testserver via wsgiref on port 8000.

End-to-end coverage of the WSGI adapter lives in
quixote/test/test_wsgi.py, which drives it directly without a live server.
