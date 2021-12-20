"""Logic for publishing modules and objects on the Web.
"""

import sys, traceback, io
import time
import urllib.parse
import cgitb

from quixote.errors import (
    PublishError,
    MethodNotAllowedError,
    format_publish_error,
    INTERNAL_ERROR_MESSAGE,
)
from quixote import util
from quixote.config import Config
from quixote.http_response import HTTPResponse
from quixote.http_request import HTTPRequest
from quixote.logger import DefaultLogger


class Publisher:
    """
    The core of Quixote and of any Quixote application.  This class is
    responsible for converting each HTTP request into a traversal of the
    application's directory tree and, ultimately, a call of a Python
    function/method/callable object.

    Each invocation of a driver script should have one Publisher
    instance that lives for as long as the driver script itself.  Eg. if
    your driver script is plain CGI, each Publisher instance will handle
    exactly one HTTP request; if you have a FastCGI driver, then each
    Publisher will handle every HTTP request handed to that driver
    script process.

    Instance attributes:
      root_directory : Directory
        the root directory that will be searched for objects to fulfill
        each request.  This can be any object with a _q_traverse method
        that acts like Directory._q_traverse.
      logger : DefaultLogger
        controls access log and error log behavior
      session_manager : NullSessionManager
         keeps track of sessions
      config : Config
        holds all configuration info for this application.  If the
        application doesn't provide values then default values
        from the quixote.config module are used.
      _request : HTTPRequest
        the HTTP request currently being processed.
    """

    def __init__(
        self,
        root_directory,
        logger=None,
        session_manager=None,
        config=None,
        **kwargs,
    ):
        global _publisher
        if config is None:
            self.config = Config(**kwargs)
        else:
            if kwargs:
                raise ValueError(
                    "cannot provide both 'config' object and"
                    " config arguments"
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

    def set_session_manager(self, session_manager):
        self.session_manager = session_manager

    def log(self, msg):
        self.logger.log(msg)

    def parse_request(self, request):
        """Parse the request information waiting in 'request'."""
        request.process_inputs()

    def start_request(self):
        """Called at the start of each request."""
        self.session_manager.start_request()

    def _set_request(self, request):
        """Set the current request object."""
        self._request = request

    def _clear_request(self):
        """Unset the current request object."""
        self._request = None

    def get_request(self):
        """Return the current request object."""
        return self._request

    def finish_successful_request(self):
        """Called at the end of a successful request."""
        self.session_manager.finish_successful_request()

    def format_publish_error(self, exc):
        return format_publish_error(exc)

    def finish_interrupted_request(self, exc):
        """
        Called at the end of an interrupted request.  Requests are
        interrupted by raising a PublishError exception.  This method
        should return a string object which will be used as the result of
        the request.
        """
        if not self.config.display_exceptions and exc.private_msg:
            exc.private_msg = None  # hide it
        request = get_request()
        request.response = HTTPResponse(status=exc.status_code)
        output = self.format_publish_error(exc)
        self.session_manager.finish_successful_request()
        return output

    def finish_failed_request(self):
        """
        Called at the end of an failed request.  Any exception (other
        than PublishError) causes a request to fail.  This method should
        return a string object which will be used as the result of the
        request.
        """
        # build new response to be safe
        request = get_request()
        original_response = request.response
        request.response = HTTPResponse()
        # self.log("caught an error (%s), reporting it." %
        #         sys.exc_info()[1])

        (exc_type, exc_value, tb) = sys.exc_info()
        error_summary = traceback.format_exception_only(exc_type, exc_value)
        error_summary = error_summary[0][0:-1]  # de-listify and strip newline

        plain_error_msg = self._generate_plaintext_error(
            request, original_response, exc_type, exc_value, tb
        )

        if not self.config.display_exceptions:
            # DISPLAY_EXCEPTIONS is false, so return the most
            # secure (and cryptic) page.
            request.response.set_header("Content-Type", "text/html")
            user_error_msg = self._generate_internal_error(request)
        elif self.config.display_exceptions == 'html':
            # Generate a spiffy HTML display using cgitb
            request.response.set_header("Content-Type", "text/html")
            user_error_msg = self._generate_cgitb_error(
                request, original_response, exc_type, exc_value, tb
            )
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

    def _generate_internal_error(self, request):
        return INTERNAL_ERROR_MESSAGE

    def _generate_plaintext_error(
        self, request, original_response, exc_type, exc_value, tb
    ):
        error_file = io.StringIO()

        # format the traceback
        traceback.print_exception(exc_type, exc_value, tb, file=error_file)

        # include request and response dumps
        error_file.write('\n')
        error_file.write(request.dump())
        error_file.write('\n')

        return error_file.getvalue()

    def _generate_cgitb_error(
        self, request, original_response, exc_type, exc_value, tb
    ):
        # let cgitb.Hook have the type it wants...
        error_file = io.StringIO()
        hook = cgitb.Hook(file=error_file)
        hook(exc_type, exc_value, tb)

        byte_error_file = io.BytesIO()
        byte_error_file.write(b'<h2>Original Request</h2>')
        # dump_request returns an HTMLText object
        s = str(util.dump_request(request))
        byte_error_file.write(s.encode('latin-1', 'strict'))
        byte_error_file.write(b'<h2>Original Response</h2><pre>')
        original_response.write(byte_error_file)
        byte_error_file.write(b'</pre>')
        # Now we push the bytes to the "real" error file...
        s = byte_error_file.getvalue().decode('latin-1')
        error_file.write(s)

        return error_file.getvalue()

    def try_publish(self, request):
        """(request : HTTPRequest) -> object

        The master method that does all the work for a single request.
        Exceptions are handled by the caller.
        """
        self.start_request()
        method = request.get_method()
        allowed_methods = self.config.allowed_methods
        if allowed_methods is not None and method not in allowed_methods:
            raise MethodNotAllowedError(allowed_methods)
        path = request.get_environ('PATH_INFO', '')
        if path and path[:1] != '/':
            return redirect(
                request.get_environ('SCRIPT_NAME', '') + '/' + path,
                permanent=True,
            )
        components = path[1:].split('/')
        output = self.root_directory._q_traverse(components)
        # The callable ran OK, commit any changes to the session
        self.finish_successful_request()
        return output

    def filter_output(self, request, output):
        """Hook for post processing the output.  Subclasses may wish to
        override (e.g. check HTML syntax).
        """
        return output

    def process_request(self, request):
        """(request : HTTPRequest) -> HTTPResponse

        Process a single request, given an HTTPRequest object.  The
        try_publish() method will be called to do the work and
        exceptions will be handled here.
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

    def process(self, stdin, env):
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
_publisher = None


def get_publisher():
    return _publisher


def get_request():
    return _publisher.get_request()


def get_response():
    return _publisher.get_request().response


def get_field(name, default=None):
    """Return the query parameter or form field named 'name'.  If
    it doesn't exist then return 'default'.  If a query parameter
    is appears multiple times, a list of values is returned.
    """
    return _publisher.get_request().get_field(name, default)


def get_param(name, default=None):
    """Return the query parameter or form field named 'name'.  If
    it doesn't exist then return 'default'.  If a query parameter
    is appears multiple times, return the last value specified.
    """
    value = _publisher.get_request().get_field(name, default)
    if isinstance(value, list):
        if value:
            return value[-1]
        else:
            return default
    return value


def get_cookie(name, default=None):
    return _publisher.get_request().get_cookie(name, default)


def get_path(n=0):
    return _publisher.get_request().get_path(n)


def redirect(location, permanent=False):
    """(location : string, permanent : boolean = false) -> string

    Create a redirection response.  If the location is relative, then it
    will automatically be made absolute.  The return value is an HTML
    document indicating the new URL (useful if the client browser does
    not honor the redirect).
    """
    request = _publisher.get_request()
    location = urllib.parse.urljoin(request.get_url(), str(location))
    return request.response.redirect(location, permanent)


def get_session():
    return _publisher.get_request().session


def get_session_manager():
    return _publisher.session_manager


def get_user():
    session = _publisher.get_request().session
    if session is None:
        return None
    else:
        return session.user


def get_wsgi_app():
    from quixote.wsgi import QWIP

    return QWIP(_publisher)


def cleanup():
    global _publisher
    _publisher = None
