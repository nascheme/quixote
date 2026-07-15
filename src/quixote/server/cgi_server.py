#!/usr/bin/env python3
"""CGI server adapter.

Publishes a Quixote application as a CGI script: one process per request,
reading from stdin and the CGI environment.  Use `run` from a driver script.
"""

from __future__ import annotations

import os
import sys
from collections.abc import Callable
from typing import Any, cast

from quixote.publish import Publisher

CreatePublisher = Callable[[], Publisher]


def run(create_publisher: CreatePublisher) -> None:
    """Serve a single CGI request and exit.

    `create_publisher` is a zero-argument factory returning a `Publisher`.
    The request is read from stdin and the CGI environment, and the response
    is written to stdout; the process handles exactly one request, as the CGI
    model requires.
    """
    if sys.platform == "win32":
        # on Windows, stdin and stdout are in text mode by default
        import msvcrt

        msvcrt.setmode(sys.__stdin__.fileno(), os.O_BINARY)
        msvcrt.setmode(sys.__stdout__.fileno(), os.O_BINARY)
    publisher = create_publisher()
    response = publisher.process(cast(Any, sys.__stdin__), os.environ)
    try:
        response.write(cast(Any, sys.__stdout__))
    except IOError as err:
        publisher.log("IOError while sending response ignored: %s" % err)


if __name__ == '__main__':
    from quixote.demo import create_publisher

    run(create_publisher)
