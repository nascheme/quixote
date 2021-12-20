"""Quixote

A small and flexible Python web application framework.
"""

__version__ = '3.6a2'

# These are frequently needed by Quixote applications.
from quixote.publish import (  # noqa: F401
    get_publisher,
    get_request,
    get_response,
    get_path,
    redirect,
    get_session,
    get_session_manager,
    get_user,
    get_field,
    get_cookie,
    get_wsgi_app,
    cleanup,
    get_param,
)


# This is the default charset used by the HTTPRequest, HTTPResponse,
# DefaultLogger, and sendmail components.
DEFAULT_CHARSET = 'utf-8'


def enable_ptl():
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
