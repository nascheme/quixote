"""The publisher: turning HTTP requests into responses.

The `Publisher` drives every request.  It creates an `HTTPRequest`, hands
the URL path to the application's root `Directory` for traversal, and turns
the returned page content into an `HTTPResponse`.  It catches `PublishError`
and unexpected exceptions raised while parsing and publishing the request;
failures during error rendering, output filtering, response finalization, or
logging can still propagate.

A process has exactly one `Publisher`, created at startup by a server
adapter (see `quixote.server`).  Application code rarely touches it
directly; instead it uses the module-level helpers -- `get_request`,
`get_response`, `get_session`, `get_user`, `get_field` / `get_param`,
`get_path`, `get_cookie`, and `redirect` -- which act on the request
stored on the publisher.

These helpers operate on the publisher's stored request.  Helpers that need
a request raise `RuntimeError` when none is stored; others return None when
their target is unavailable.  Each `current_*` counterpart --
`current_publisher`, `current_request`, `current_response`,
`current_session`, `current_user`, `current_session_manager` -- raises
`RuntimeError` instead of returning None.
"""

from __future__ import annotations

import io
import sys
import time
import traceback
import urllib.parse
from types import TracebackType
from typing import IO, TYPE_CHECKING, TypeVar, cast

import quixote.directory as _directory
from quixote.config import Config
from quixote.errors import (
    INTERNAL_ERROR_MESSAGE,
    MethodNotAllowedError,
    PublishError,
    Rendered,
    format_publish_error,
)
from quixote.http_request import Environ, FieldItem, FieldValue, HTTPRequest
from quixote.http_response import HTTPResponse
from quixote.logger import DefaultLogger

if TYPE_CHECKING:
    from quixote.directory import Directory
    from quixote.session import BaseSessionManager, Session
    from quixote.wsgi import QWIP

_T = TypeVar('_T')


class Publisher:
    """Converts each HTTP request into a directory traversal and a response.

    The `Publisher` is the core of any Quixote application: for each
    request it walks the application's `Directory` tree to find a callable
    endpoint, calls it, and packages the result as an `HTTPResponse`.

    A process has exactly one `Publisher`; constructing a second one raises
    `RuntimeError`.  A server adapter creates it at startup and calls
    `process` (or `process_request`) per request.  Retrieve it anywhere with
    `get_publisher`.

    Applications commonly subclass `Publisher` to override request-lifecycle
    hooks -- `start_request`, `parse_request`, `try_publish`,
    `filter_output`, `format_publish_error`, `finish_successful_request` --
    and use that subclass from the zero-argument publisher factory passed to
    their server adapter.

    Instance attributes:
      root_directory : Directory
        the root searched to fulfill each request; any object with a
        `_q_traverse` method that behaves like `Directory._q_traverse`.
      logger : DefaultLogger
        controls access-log and error-log behaviour.
      session_manager : BaseSessionManager
        keeps track of sessions (a `NullSessionManager` if none is supplied).
      config : Config
        all configuration for this application; unset values fall back to the
        defaults in `quixote.config`.
      _request : HTTPRequest | None
        the request slot used by the helper functions; set at the start of
        processing and cleared only when `process_request` returns normally.
    """

    is_thread_safe: bool = False

    root_directory: Directory
    logger: DefaultLogger
    session_manager: BaseSessionManager
    config: Config
    _request: HTTPRequest | None

    def __init__(
        self,
        root_directory: Directory,
        logger: DefaultLogger | None = None,
        session_manager: BaseSessionManager | None = None,
        config: Config | None = None,
        **kwargs: object,
    ) -> None:
        """Create the process's single Publisher.

        `root_directory` is the top of the application's `Directory` tree and
        must have a callable `_q_traverse` method.  A missing attribute raises
        `AttributeError`; a present but non-callable one raises `TypeError`.
        If `logger` or `session_manager` are omitted, a `DefaultLogger` and a
        `NullSessionManager` are used.  Configuration comes either from a
        `Config` passed as `config` or from keyword arguments used to build
        one -- supplying both raises `ValueError`.  Constructing a second
        Publisher in the same process raises `RuntimeError`; call `cleanup`
        first to release the existing one.
        """
        global _publisher
        if config is None:
            self.config = Config(**kwargs)
        else:
            if kwargs:
                raise ValueError(
                    "cannot provide both 'config' object and config arguments"
                )
            self.config = config
        if logger is None:
            self.logger = DefaultLogger(
                error_log=self.config.error_log,
                access_log=self.config.access_log,
                error_email=self.config.error_email,
            )
        else:
            self.logger = logger
        if session_manager is not None:
            self.session_manager = session_manager
        else:
            from quixote.session import NullSessionManager

            self.session_manager = NullSessionManager()

        if self.config.display_exceptions:
            # Assume we are in "dev" mode and enable this warning.
            _directory.WARN_TRAILING_SLASH = True

        if _publisher is not None:
            raise RuntimeError("only one instance of Publisher allowed")
        _publisher = self

        if not callable(root_directory._q_traverse):
            raise TypeError(
                'Expected something with a _q_traverse method, got %r'
                % root_directory
            )
        self.root_directory = root_directory
        self._request = None

    def set_session_manager(
        self,
        session_manager: BaseSessionManager,
    ) -> None:
        """Replace the session manager after construction."""
        self.session_manager = session_manager

    def log(self, msg: str) -> None:
        """Write `msg` to the application's error log via the logger."""
        self.logger.log(msg)

    def parse_request(self, request: HTTPRequest) -> None:
        """Parse the request information waiting in 'request'."""
        request.process_inputs()

    def start_request(self) -> None:
        """Called at the start of each request."""
        self.session_manager.start_request()

    def _set_request(self, request: HTTPRequest) -> None:
        """Set the current request object."""
        self._request = request

    def _clear_request(self) -> None:
        """Unset the current request object."""
        self._request = None

    def get_request(self) -> HTTPRequest | None:
        """Return the publisher's stored request, or None.

        `process_request` sets this before parsing and clears it only when it
        returns normally; if request processing escapes with an exception, the
        stored request may be stale.  Use module-level `current_request` to
        get a request that is guaranteed to be non-None.
        """
        return self._request

    def finish_successful_request(self) -> None:
        """Called at the end of a successful request."""
        self.session_manager.finish_successful_request()

    def format_publish_error(self, exc: PublishError) -> Rendered:
        """Render an interrupted request's `PublishError` into page content.

        Override to customise error pages (branding, logging, content type).
        The default defers to `quixote.errors.format_publish_error`.
        """
        return format_publish_error(exc)

    def finish_interrupted_request(self, exc: PublishError) -> Rendered:
        """
        Called at the end of an interrupted request.  Requests are
        interrupted by raising a PublishError exception.  This method
        should return a string object which will be used as the result of
        the request.
        """
        if not self.config.display_exceptions and exc.private_msg:
            exc.private_msg = None  # hide it
        request = current_request()
        request.response = HTTPResponse(status=exc.status_code)
        output = self.format_publish_error(exc)
        self.session_manager.finish_successful_request()
        return output

    def finish_failed_request(self) -> Rendered:
        """
        Called at the end of an failed request.  Any exception (other
        than PublishError) causes a request to fail.  This method should
        return a string object which will be used as the result of the
        request.
        """
        # build new response to be safe
        request = current_request()
        original_response = request.response
        request.response = HTTPResponse()
        # self.log("caught an error (%s), reporting it." %
        #         sys.exc_info()[1])

        exc_type, exc_value, tb = cast(
            tuple[type[BaseException], BaseException, TracebackType | None],
            sys.exc_info(),
        )
        error_summary = traceback.format_exception_only(exc_type, exc_value)
        error_summary = error_summary[0][0:-1]  # de-listify and strip newline

        plain_error_msg = self._generate_plaintext_error(
            request,
            original_response,
            exc_type,
            exc_value,
            tb,
        )

        if not self.config.display_exceptions:
            # DISPLAY_EXCEPTIONS is false, so return the most
            # secure (and cryptic) page.
            request.response.set_header("Content-Type", "text/html")
            user_error_msg = self._generate_internal_error(request)
        else:
            # Generate a plaintext page containing the traceback
            request.response.set_header("Content-Type", "text/plain")
            user_error_msg = plain_error_msg

        self.logger.log_internal_error(error_summary, plain_error_msg)
        if exc_type is SystemExit:
            raise
        request.response.set_status(500)
        self.session_manager.finish_failed_request()
        return user_error_msg

    def _generate_internal_error(self, request: HTTPRequest) -> Rendered:
        return INTERNAL_ERROR_MESSAGE

    def _generate_plaintext_error(
        self,
        request: HTTPRequest,
        original_response: HTTPResponse,
        exc_type: type[BaseException],
        exc_value: BaseException,
        tb: TracebackType | None,
    ) -> str:
        del original_response
        error_file = io.StringIO()

        # format the traceback
        traceback.print_exception(exc_type, exc_value, tb, file=error_file)

        # include request and response dumps
        error_file.write('\n')
        error_file.write(request.dump())
        error_file.write('\n')

        return error_file.getvalue()

    def try_publish(self, request: HTTPRequest) -> object:
        """(request : HTTPRequest) -> object

        The master method that does all the work for a single request.
        Exceptions are handled by the caller.
        """
        self.start_request()
        method = request.get_method()
        allowed_methods = self.config.allowed_methods
        if allowed_methods is not None and method not in allowed_methods:
            raise MethodNotAllowedError(allowed_methods)
        path = cast(str, request.get_environ('PATH_INFO', ''))
        if path and path[:1] != '/':
            script_name = cast(str, request.get_environ('SCRIPT_NAME', ''))
            return redirect(script_name + '/' + path, permanent=True)
        components = path[1:].split('/')
        output = self.root_directory._q_traverse(components)
        # The callable ran OK, commit any changes to the session
        self.finish_successful_request()
        return output

    def filter_output(self, request: HTTPRequest, output: object) -> object:
        """Hook for post processing the output.  Subclasses may wish to
        override (e.g. check HTML syntax).
        """
        return output

    def process_request(self, request: HTTPRequest) -> HTTPResponse:
        """(request : HTTPRequest) -> HTTPResponse

        Process a single request, given an HTTPRequest object.
        `parse_request` and `try_publish` run under the exception handlers;
        errors raised later while filtering output, response finalization, or
        logging propagate.
        """
        self._set_request(request)
        start_time = time.time()
        try:
            self.parse_request(request)
            output = self.try_publish(request)
        except PublishError as exc:
            # Exit the publishing loop and return a result right away.
            output = self.finish_interrupted_request(exc)
        except BaseException:
            # Some other exception, generate error messages to the logs, etc.
            output = self.finish_failed_request()
        output = self.filter_output(request, output)
        if output:
            compress = False
            if self.config.compress_pages:
                if request.get_encoding(['gzip']):
                    compress = True
            if request.environ.get('SERVER_PROTOCOL') == 'HTTP/1.1':
                request.response.enable_transfer_chunked()
            request.response.set_body(output, compress)
        self.logger.log_request(request, start_time)
        self._clear_request()
        return request.response

    def process(
        self,
        stdin: IO[bytes] | None,
        env: Environ,
    ) -> HTTPResponse:
        """(stdin : stream, env : dict) -> HTTPResponse

        Process a single request, given a stream, stdin, containing the
        incoming request and a dictionary, env, containing the web server's
        environment.

        An HTTPRequest object is created and the process_request() method is
        called and passed the request object.
        """
        request = HTTPRequest(stdin, env)
        return self.process_request(request)


# Publisher singleton, only one of these per process.
_publisher: Publisher | None = None


def get_publisher() -> Publisher | None:
    """Return the process's `Publisher`, or None if none exists yet.

    There is no publisher until a server adapter constructs one.  Use
    `current_publisher` to get a publisher that is guaranteed to be
    non-None.
    """
    return _publisher


def current_publisher() -> Publisher:
    """Return the process's `Publisher`, or raise `RuntimeError` if none.

    Like `get_publisher` but never returns None, so it is convenient when
    a publisher is known to exist (e.g. while handling a request).
    """
    publisher = _publisher
    if publisher is None:
        raise RuntimeError('no active publisher')
    return publisher


def get_request() -> HTTPRequest | None:
    """Return the `HTTPRequest` stored on the active publisher, or None.

    None is returned if no publisher exists or no request is stored.  The
    request slot is cleared only when `Publisher.process_request` returns
    normally; after escaped processing exceptions it may be stale.  Use
    `current_request` to get a request that is guaranteed to be non-None.
    """
    if _publisher is None:
        return None
    return _publisher.get_request()


def current_request() -> HTTPRequest:
    """Return the `HTTPRequest` stored on the active publisher.

    Like `get_request` but raises `RuntimeError` instead of returning None,
    so it is only valid when a request is known to be stored.
    """
    request = get_request()
    if request is None:
        raise RuntimeError('no active request')
    return request


def get_response() -> HTTPResponse | None:
    """Return the `HTTPResponse` for the stored request, or None.

    None is returned if no request is stored.  Use `current_response` to get a
    response that is guaranteed to be non-None.
    """
    request = get_request()
    if request is None:
        return None
    return request.response


def current_response() -> HTTPResponse:
    """Return the `HTTPResponse` for the stored request.

    Like `get_response` but raises `RuntimeError` instead of returning None,
    so it is only valid when a request is known to be stored.
    """
    return current_request().response


def get_field(
    name: str,
    default: _T | None = None,
) -> FieldValue | _T | None:
    """Return the query parameter or form field named `name`.

    Returns `default` if it is not present.  If the parameter appears more
    than once, the full list of values is returned; use `get_param` instead
    to get a single value.  Raises `RuntimeError` if no request is stored.
    """
    return current_request().get_field(name, default)


def get_param(
    name: str,
    default: _T | None = None,
) -> FieldItem | _T | None:
    """Return a single value for the query parameter or form field `name`.

    Returns `default` if it is not present.  If the parameter appears more
    than once, the last value is returned; use `get_field` instead to get
    the whole list.  Raises `RuntimeError` if no request is stored.
    """
    value = current_request().get_field(name, default)
    if isinstance(value, list):
        if value:
            return value[-1]
        else:
            return default
    return value


def get_cookie(
    name: str | None,
    default: _T | None = None,
) -> str | _T | None:
    """Return the value of request cookie `name`, or `default` if unset.

    A `name` of None also returns `default`.  Raises `RuntimeError` if no
    request is stored.
    """
    if name is None:
        return default
    return current_request().get_cookie(name, default)


def get_path(n: int = 0) -> str:
    """Return the request's URL path, adjusted by `n` path components.

    ``get_path(0)`` is the full path.  Positive `n` drops components from the
    right; negative `n` returns components from the left.  Excessive positive
    or negative values raise `ValueError`.  Raises `RuntimeError` if no
    request is stored.
    """
    return current_request().get_path(n)


def redirect(location: object, permanent: bool | int = False) -> str:
    """Redirect the current response to `location` and return fallback text.

    A relative `location` is resolved against the current request URL.  Sets
    the response status to 302, or 301 when `permanent` is true.  The returned
    string is a short plain-text body naming the new URL, shown by clients
    that do not follow the redirect; typical usage is ``return redirect(...)``
    from an exported method.  Raises `RuntimeError` if no request is stored.
    """
    request = current_request()
    absolute_location = urllib.parse.urljoin(request.get_url(), str(location))
    return request.response.redirect(absolute_location, permanent)


def get_session() -> Session | None:
    """Return the current request's `Session`, or None if there is none.

    Whether a session exists depends on the publisher's session manager; with
    the default `NullSessionManager` this returns None.  None is also returned
    if no request is stored.
    """
    from quixote.session import Session

    request = get_request()
    if request is None:
        return None
    return cast(Session | None, request.session)


def current_session() -> Session:
    """Return the current request's `Session`.

    Like `get_session` but raises `RuntimeError` instead of returning None.
    Only valid while handling a request, with a session manager that creates
    sessions (not the default `NullSessionManager`).
    """
    session = get_session()
    if session is None:
        raise RuntimeError('no session for the active request')
    return session


def get_session_manager() -> BaseSessionManager | None:
    """Return the publisher's session manager, or None if no publisher."""
    from quixote.session import BaseSessionManager

    publisher = get_publisher()
    if publisher is None:
        return None
    return cast(BaseSessionManager, publisher.session_manager)


def current_session_manager() -> BaseSessionManager:
    """Return the publisher's session manager.

    Like `get_session_manager` but raises `RuntimeError` instead of
    returning None when there is no publisher.
    """
    from quixote.session import BaseSessionManager

    return cast(BaseSessionManager, current_publisher().session_manager)


def get_user() -> object | None:
    """Return the user object stored on the current session, or None.

    This is whatever the application stored via `Session.set_user`; Quixote
    itself attaches no meaning to it.  Returns None if no request is stored,
    no session exists, or no user has been set.
    """
    session = get_session()
    if session is None:
        return None
    else:
        return session.user


def current_user() -> object:
    """Return the user object stored on the current session.

    Like `get_user` but raises `RuntimeError` instead of returning None, so
    it is only valid while handling a request from a logged-in user (i.e.
    after the application has called `Session.set_user`).
    """
    user = get_user()
    if user is None:
        raise RuntimeError('no user set on the active session')
    return user


def get_wsgi_app() -> QWIP:
    """Return a WSGI application wrapping the active publisher.

    The default publisher is not thread-safe, so the WSGI server must not set
    ``wsgi.multithread`` unless the publisher declares itself thread-safe.
    See `quixote.wsgi`.  Raises `RuntimeError` if there is no publisher.
    """
    from quixote.wsgi import QWIP

    return QWIP(current_publisher())


def cleanup() -> None:
    """Discard the process's `Publisher` so a new one can be created.

    Mainly useful in tests and teardown; after this, publisher/session lookup
    helpers return None and the `current_*` helpers raise `RuntimeError` until
    another `Publisher` is constructed.
    """
    global _publisher
    _publisher = None
