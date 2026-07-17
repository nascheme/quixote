"""Exception classes for aborting a request with an error page.

Raising any `PublishError` subclass during publishing aborts the current
request: the publisher catches it, sends the exception's `status_code`, and
renders an error page from its `format` method.  The concrete subclasses map
to HTTP statuses -- `TraversalError` (404), `QueryError` (400),
`RequestError` (400), `AccessError` (403), `MethodNotAllowedError` (405) --
and applications raise them directly.  Subclass `PublishError` for custom
errors that need their own status code, title, or formatting.
"""

from collections.abc import Sequence

import quixote
from quixote.html import htmlescape, htmltext

type Rendered = str | htmltext


class PublishError(Exception):
    """PublishError exceptions are raised due to some problem with the
    data provided by the client and are raised during the publishing
    process.  Quixote will abort the current request and return an error
    page to the client.

    public_msg should be a user-readable message that reveals no
    inner workings of your application; it will always be shown.

    private_msg carries developer-facing detail and is stored as given.
    During normal publishing, Quixote clears it before rendering when
    DISPLAY_EXCEPTIONS is false.  Direct `format` calls include any
    private_msg still present, so do not expose formatted errors unless the
    publisher has applied that policy.  (DISPLAY_EXCEPTIONS should always be
    false in a production environment, since these details about the inner
    workings of your application could conceivably be useful to attackers.)

    The formatting done by the Quixote versions of these exceptions is
    very simple.  Applications will probably wish to raise application
    specific subclasses which do more sophisticated formatting or provide
    a _q_except handler to format the exception.

    """

    public_msg: str | None
    private_msg: str | None

    status_code = 400  # bad request
    title = "Publishing error"
    description = (
        "An error occured while generating the requested page. "
        "For help, please contact the site administrator."
    )

    def __init__(
        self, public_msg: str | None = None, private_msg: str | None = None
    ) -> None:
        """Create the error with an optional public and private message.

        public_msg is shown by the default renderer, so it must not leak
        internal detail.  private_msg is developer-facing detail stored as
        given; the publisher clears it before rendering when
        DISPLAY_EXCEPTIONS is false.
        """
        self.public_msg = public_msg
        self.private_msg = (
            private_msg  # cleared if DISPLAY_EXCEPTIONS is false
        )

    def __str__(self) -> str:
        return self.private_msg or self.public_msg or "???"

    def format(self) -> Rendered:
        """Return the HTML fragment shown in the error page body.

        Override in a subclass to change how the error is presented.
        """
        msg = htmlescape(self.title)
        if self.public_msg:
            msg = msg + ": " + self.public_msg
        if self.private_msg:
            msg = msg + ": " + self.private_msg
        return msg


class TraversalError(PublishError):
    """
    Rendered as HTTP 404.  Raised when a client attempts to access a
    resource that does not exist or is otherwise unavailable to them (eg. a
    name neither listed in a directory's _q_exports nor dynamically resolved).
    Application `Directory._q_lookup` and `_q_traverse` overrides raise this
    for unknown path components.

    path should be the path to the requested resource; if not
    supplied, the current request object will be fetched and its
    get_path() method called.
    """

    status_code = 404  # not found
    title = "Page not found"
    description = (
        "The requested link does not exist on this site.  If "
        "you arrived here by following a link from an external "
        "page, please inform that page's maintainer."
    )

    def __init__(
        self,
        public_msg: str | None = None,
        private_msg: str | None = None,
        path: str | None = None,
    ) -> None:
        """Like `PublishError.__init__`, but also records the requested path.

        path defaults to the current request's path when not given, which
        requires an active request and raises `RuntimeError` otherwise.
        """
        PublishError.__init__(self, public_msg, private_msg)
        if path is None:
            path = quixote.current_request().get_path()
        self.path = path

    def format(self) -> Rendered:
        """Include the requested path in the rendered message."""
        msg = htmlescape(self.title) + ": " + self.path
        if self.public_msg:
            msg = msg + ": " + self.public_msg
        if self.private_msg:
            msg = msg + ": " + self.private_msg
        return msg


class RequestError(PublishError):
    """
    Rendered as HTTP 400.  Raised when Quixote is unable to parse an HTTP
    request (or its CGI representation).  This is a lower-level error than
    QueryError -- it either means that Quixote is not smart enough to handle
    the request being passed to it, or the user-agent is broken and/or
    malicious.
    """

    status_code = 400
    title = "Invalid request"
    description = "Unable to parse HTTP request."


class QueryError(PublishError):
    """Rendered as HTTP 400.  Should be raised if bad data was provided in the
    query part of a URL or in the content of a POST request.  What constitutes
    bad data is solely application dependent (eg: letters in a form field when
    the application expects a number).
    """

    status_code = 400
    title = "Invalid query"
    description = (
        "An error occurred while handling your request.  The "
        "query data provided as part of the request is invalid."
    )


class AccessError(PublishError):
    """Rendered as HTTP 403.  Should be raised if the client does not have
    access to the requested resource.  Usually applications will raise this
    error from an _q_access method or a _q_traverse override.
    """

    status_code = 403
    title = "Access denied"
    description = (
        "An error occurred while handling your request.  "
        "Access to the requested resource was not permitted."
    )


class MethodNotAllowedError(PublishError):
    """Rendered as HTTP 405.  Raised when the request's HTTP method is not
    permitted for the resource, e.g. a POST to a read-only endpoint.  Raise it
    with the methods that are allowed; `format` reports them and sets the
    required ``Allow`` response header.
    """

    status_code = 405
    title = "Method not allowed"
    description = (
        "The method specified in the request is not allowed for "
        "the resource identified by the URI."
    )

    def __init__(self, allowed_methods: Sequence[str]) -> None:
        """Record the HTTP methods permitted for this resource."""
        self.allowed_methods = allowed_methods
        self.public_msg = self.private_msg = None

    def format(self) -> Rendered:
        """Set the ``Allow`` header and render the allowed methods.

        Requires an active request; otherwise `current_response` raises
        `RuntimeError`.
        """
        allowed_methods = ', '.join(self.allowed_methods)
        quixote.current_response().set_header('Allow', allowed_methods)
        return 'Allowed methods are: %s' % allowed_methods


PAGE_TEMPLATE = htmltext('''\
<!DOCTYPE html>
<html>
<head>
<title>%(title)s</title>
<style type="text/css">
body {
    font: 13px arial,helvetica,clean,sans-serif;
}
h1 {
    font-size: 24px;
}
p {
    width: 40em;
}
</style>
</head>
<body>
    <h1>%(title)s</h1>
    %(body)s
</body>
</html>
''')


def format_page(title: object, body: object) -> Rendered:
    """Used for Quixote generated HTML pages.  This function can be replaced
    to ensure you application has a consistent look to web pages.  Be aware
    that this function should do a minimal amount of processing since it can
    be called when the server encounters an error.
    """
    return PAGE_TEMPLATE % dict(title=title, body=body)


ERROR_BODY = htmltext('''
    <p>%(description)s</p>
    <p>%(details)s</p>
''')


def format_error_page(
    title: object, description: object, details: object
) -> Rendered:
    """Render a titled error page with a description and detail paragraph.

    Wraps the body in `format_page`; used to build both PublishError pages
    and the internal-error page.
    """
    body = ERROR_BODY % dict(description=description, details=details)
    return format_page(title=title, body=body)


# Error message to dispay for non-PublishError exception when
# DISPLAY_EXCEPTIONS is set to None.  If DISPLAY_EXCEPTIONS is not
# None than a traceback will displayed.
INTERNAL_ERROR_MESSAGE = format_error_page(
    title='Internal Server Error',
    description=(
        'An internal error occured while handling your page request.'
    ),
    details=(
        'The error has been logged but you may wish to contact the '
        'server administrator and inform them of the time the error '
        'occurred, and anything you might have done to trigger the '
        'error.'
    ),
)


def format_publish_error(exc: PublishError) -> Rendered:
    """Render a `PublishError` as a complete error page.

    Combines the exception's title, description, and `format` output.  This
    is the default used by `Publisher.format_publish_error`; applications
    should override that method to customize error pages.
    """
    return format_error_page(
        title='Error: %s' % exc.title,
        description=exc.description,
        details=exc.format(),
    )
