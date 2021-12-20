"""
QWIP: a simple yet functional Quixote/WSGI application-side adapter for
Quixote 2.x.

To create an application object, execute

     app_obj = QWIP(publisher)

Authors: Mike Orr <mso@oz.net> and Titus Brown <titus@caltech.edu>.
Last updated 2005-05-03.
"""

from .http_request import HTTPRequest

###### QWIP: WSGI COMPATIBILITY WRAPPER FOR QUIXOTE #####################


class QWIP:
    """I make a Quixote Publisher object look like a WSGI application."""

    request_class = HTTPRequest

    def __init__(self, publisher):
        self.publisher = publisher

    def __call__(self, env, start_response):
        """I am called for each request."""
        if env.get('wsgi.multithread') and not getattr(
            self.publisher, 'is_thread_safe', False
        ):
            reason = "%r is not thread safe" % self.publisher
            raise AssertionError(reason)
        if 'REQUEST_URI' not in env:
            env['REQUEST_URI'] = env['SCRIPT_NAME'] + env['PATH_INFO']
        input = env['wsgi.input']
        request = self.request_class(input, env)
        response = self.publisher.process_request(request)
        status = "%03d %s" % (response.status_code, response.reason_phrase)
        headers = response.generate_headers()
        start_response(status, headers)
        return response.generate_body_chunks()  # Iterable object.
