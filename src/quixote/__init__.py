"""Quixote

A small and flexible Python web application framework.
"""

from quixote._version import __version__  # noqa: F401

# These are frequently needed by Quixote applications.
from quixote.publish import (  # noqa: F401
    cleanup,
    current_publisher,
    current_request,
    current_response,
    current_session,
    current_session_manager,
    current_user,
    get_cookie,
    get_field,
    get_param,
    get_path,
    get_publisher,
    get_request,
    get_response,
    get_session,
    get_session_manager,
    get_user,
    get_wsgi_app,
    redirect,
)

# This is the default charset used by the HTTPRequest, HTTPResponse,
# DefaultLogger, and sendmail components.
DEFAULT_CHARSET = 'utf-8'


def enable_ptl() -> None:
    """
    Installs the import hooks needed to import PTL modules.  This must
    be done explicitly because not all Quixote applications need to use
    PTL, and import hooks are deep magic that can cause all sorts of
    mischief and deeply confuse innocent bystanders.  Thus, we avoid
    invoking them behind the programmer's back.  One known problem is
    that, if you use ZODB, you must import ZODB before calling this
    function.
    """
    import quixote.ptl.install  # noqa: F401
