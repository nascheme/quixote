from __future__ import annotations

import os
import socket
import sys
import time
from typing import TYPE_CHECKING, TextIO, cast

import quixote
from quixote.sendmail import sendmail

if TYPE_CHECKING:
    from quixote.http_request import HTTPRequest
    from quixote.session import Session


class DefaultLogger:
    """
    This is the default logger object used by the Quixote publisher.  It
    controls access log and error log behavior.  You may provide your own
    object if you wish to have different behavior.

    Instance attributes:

      access_log : file | None
        file to which every access will be logged.  If None then access
        is not logged.
      error_log : file
        file to which application errors (exceptions caught by Quixote,
        as well as anything printed to stdout by application code) will
        be logged.  Set to sys.stderr by default.
      error_email : string | None
        if set then `log_internal_error` tries to mail internal server
        errors to this address.  Delivery uses `quixote.sendmail` and
        needs a process `Publisher` with usable mail settings; mail
        setup, connection, or SMTP errors are not caught here.
    """

    DEFAULT_CHARSET: str | None = None  # defaults to quixote.DEFAULT_CHARSET

    access_log: TextIO | None
    error_log: TextIO
    error_email: str | None

    def __init__(
        self,
        access_log: str | None = None,
        error_log: str | None = None,
        error_email: str | None = None,
    ) -> None:
        """Open the log files named by the arguments.

        `access_log` and `error_log` are filenames; a falsy `access_log`
        disables access logging, and a `None` `error_log` sends errors to
        stderr.  When `error_email` is set, internal errors are also
        passed to `log_internal_error`'s mail path, which needs a process
        `Publisher` with usable mail settings; sendmail failures propagate.
        Opening a logger redirects `sys.stdout` to the error log so that
        stray prints in application code are captured.
        """
        if access_log:
            self.access_log = self._open_log(access_log)
        else:
            self.access_log = None
        if error_log is None:
            self.error_log = sys.stderr
        else:
            self.error_log = self._open_log(error_log)
        self.error_email = error_email
        sys.stdout = self.error_log  # print is handy for debugging

    def _open_log(self, filename: str) -> TextIO:
        charset = self.DEFAULT_CHARSET or quixote.DEFAULT_CHARSET
        return open(
            filename,
            'a',
            encoding=charset,
            buffering=1,
            errors='xmlcharrefreplace',
        )

    def log(self, msg: str) -> None:
        """
        Write an message to the error log with a time stamp.
        """
        timestamp = time.strftime(
            "%Y-%m-%d %H:%M:%S", time.localtime(time.time())
        )
        self.error_log.write("[%s] %s%s" % (timestamp, msg, os.linesep))

    def log_internal_error(self, error_summary: str, error_msg: str) -> None:
        """Log an uncaught application error, and mail it if configured.

        `error_summary` is a single-line summary suitable for an email
        subject; `error_msg` is the multi-line plaintext detail (usually a
        traceback).  The message is always written to the error log.  When
        `error_email` is set it is also passed to `quixote.sendmail`, which
        uses the process `Publisher` for SMTP settings; configuration,
        connection, or SMTP errors from `sendmail` are not caught here.
        """
        self.log("exception caught")
        self.error_log.write(error_msg)
        if self.error_email:
            sendmail(
                'Quixote Traceback (%s)' % error_summary,
                error_msg,
                [self.error_email],
                from_addr=(self.error_email, socket.gethostname()),
            )

    def log_request(self, request: HTTPRequest, start_time: float) -> None:
        """Log a request in the access_log file."""
        if self.access_log is None:
            return
        session = cast(Session | None, request.session)
        if session:
            user = session.user or "-"
        else:
            user = "-"
        now = time.time()
        seconds = now - start_time
        timestamp = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(now))

        request_uri = request.get_path()
        query = request.get_query()
        if query:
            request_uri += "?" + query
        proto = request.get_environ('SERVER_PROTOCOL')
        self.access_log.write(
            '%s %s %s %d "%s %s %s" %s %r %0.3fs%s'
            % (
                request.get_environ('REMOTE_ADDR'),
                user,
                timestamp,
                os.getpid(),
                request.get_method(),
                request_uri,
                proto,
                request.response.status_code,
                request.get_environ('HTTP_USER_AGENT', ''),
                seconds,
                os.linesep,
            )
        )
