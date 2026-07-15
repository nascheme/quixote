"""
QWIP: a simple yet functional Quixote/WSGI application-side adapter for
Quixote 2.x.

To create an application object, execute

     app_obj = QWIP(publisher)

Authors: Mike Orr <mso@oz.net> and Titus Brown <titus@caltech.edu>.
Last updated 2005-05-03.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import IO, TYPE_CHECKING, cast
from wsgiref.types import StartResponse, WSGIEnvironment

from .http_request import Environ, HTTPRequest

if TYPE_CHECKING:
    from .publish import Publisher

###### QWIP: WSGI COMPATIBILITY WRAPPER FOR QUIXOTE #####################


class QWIP:
    """I make a Quixote Publisher object look like a WSGI application."""

    request_class: type[HTTPRequest] = HTTPRequest
    publisher: Publisher

    def __init__(self, publisher: Publisher) -> None:
        """Wrap `publisher` as a WSGI application.

        The resulting object is a WSGI callable that drives `publisher` for
        each request.  Applications normally obtain one via
        `quixote.get_wsgi_app()` rather than constructing it directly.
        """
        self.publisher = publisher

    def __call__(
        self,
        env: WSGIEnvironment,
        start_response: StartResponse,
    ) -> Iterable[bytes]:
        """I am called for each request."""
        if env.get('wsgi.multithread') and not getattr(
            self.publisher, 'is_thread_safe', False
        ):
            reason = "%r is not thread safe" % self.publisher
            raise AssertionError(reason)
        if 'REQUEST_URI' not in env:
            env['REQUEST_URI'] = str(env['SCRIPT_NAME']) + str(
                env['PATH_INFO']
            )
        input = cast(IO[bytes], env['wsgi.input'])
        request = self.request_class(input, cast(Environ, env))
        response = self.publisher.process_request(request)
        status = "%03d %s" % (response.status_code, response.reason_phrase)
        headers = response.generate_headers()
        start_response(status, headers)
        return response.generate_body_chunks()  # Iterable object.
