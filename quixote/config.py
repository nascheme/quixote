"""
Quixote configuration information.  This module provides both the
default configuration values, and some code that Quixote uses for
dealing with configuration info.  You should not edit the configuration
values in this file, since your edits will be lost if you upgrade to a
newer Quixote version in the future.  However, this is the canonical
source of information about Quixote configuration variables, and editing
the defaults here is harmless if you're just playing around and don't
care what happens in the future.
"""


# Note that the default values here are geared towards a production
# environment, preferring security and performance over verbosity and
# debug-ability.  If you just want to get a Quixote application
# up-and-running in a production environment, these settings are mostly
# right; all you really need to customize are ERROR_EMAIL, and ERROR_LOG.
# If you need to test/debug/develop a Quixote application, though, you'll
# probably want to also change DISPLAY_EXCEPTIONS.
# Again, you shouldn't edit this file unless you don't care what happens
# in the future (in particular, an upgrade to Quixote would clobber your
# edits).


# E-mail address to send application errors to; None to send no mail at
# all.  This should probably be the email address of your web
# administrator.
ERROR_EMAIL = None
#ERROR_EMAIL = 'webmaster@example.com'

# Filename for writing the Quixote access log; None for no access log.
ACCESS_LOG = None
#ACCESS_LOG = "/www/log/quixote-access.log"

# Filename for logging error messages and debugging output; if None,
# everything will be sent to standard error (normally ending up in the
# Web server's error log file.
ERROR_LOG = None

# Controls what's done when uncaught exceptions occur.  If set to
# 'plain', the traceback will be returned to the browser in addition
# to being logged, If set to 'html' and the cgitb module is installed,
# a more elaborate display will be returned to the browser, showing
# the local variables and a few lines of context for each level of the
# traceback.  If set to None, a generic error display, containing no
# information about the traceback, will be used.
DISPLAY_EXCEPTIONS = None

# Compress large pages using gzip if the client accepts that encoding.
COMPRESS_PAGES = False

# If true, then a cryptographically secure token will be inserted into forms
# as a hidden field.  The token will be checked when the form is submitted.
# This prevents cross-site request forgeries (CSRF).  It is off by default
# since it doesn't work if sessions are not persistent across requests.
FORM_TOKENS = False

# A list of the HTTP request methods supported by the application.  Note that
# Quixote's support for different request methods is relatively ad hoc at
# the moment (i.e. it must be handled by application code).  If this
# variable is set to None then any method is allowed.
ALLOWED_METHODS = ['GET', 'HEAD', 'POST']

# Session-related variables
# =========================

# Name of the cookie that will hold the session ID string.
SESSION_COOKIE_NAME = "QX_session"

# Domain and path to which the session cookie is restricted.  Leaving
# these undefined is fine.  Quixote does not have a default "domain"
# option, meaning the session cookie will only be sent to the
# originating server.  If you don't set the cookie path, Quixote will
# use your application's root URL (ie. SCRIPT_NAME in a CGI-like
# environment), meaning the session cookie will be sent to all URLs
# controlled by your application, but no other.
SESSION_COOKIE_DOMAIN = None    # eg. ".example.com"
SESSION_COOKIE_PATH = None      # eg. "/"
SESSION_COOKIE_SECURE = False
SESSION_COOKIE_HTTPONLY = False


# Mail-related variables
# ======================
# These are only used by the quixote.sendmail module, which is
# provided for use by Quixote applications that need to send
# e-mail.  This is a common task for web apps, but by no means
# universal.
#
# E-mail addresses can be specified either as a lone string
# containing a bare e-mail address ("addr-spec" in the RFC 822
# grammar), or as an (address, real_name) tuple.

# MAIL_FROM is used as the default for the "From" header and the SMTP
# sender for all outgoing e-mail.  If you don't set it, your application
# will crash the first time it tries to send e-mail without an explicit
# "From" address.
MAIL_FROM = None     # eg. "webmaster@example.com"
                     # or  ("webmaster@example.com", "Example Webmaster")

# E-mail is sent by connecting to an SMTP server on MAIL_SERVER.  This
# server must be configured to relay outgoing e-mail from the current
# host (ie., the host where your Quixote application runs, most likely
# your web server) to anywhere on the Internet.  If you don't know what
# this means, talk to your system administrator.
MAIL_SERVER = "localhost"

# Port for email server.  The default port is 25.
MAIL_PORT = None

# If your SMTP server requires authentication, set these.
MAIL_USERNAME = None
MAIL_PASSWORD = None

# Enable SSL for SMTP.  The MAIL_PORT default will be 465.
MAIL_USE_SSL = False

# Enable TLS for SMTP.  The MAIL_PORT default will be 587.
MAIL_USE_TLS = False

# Allow SSLv3 as a protocol.  It is broken and disabled by default but
# some old mail servers require it.
MAIL_ALLOW_SSLV3 = False

# If MAIL_DEBUG_ADDR is set, then all e-mail will actually be sent to
# this address rather than the intended recipients.  This should be a
# single, bare e-mail address.
MAIL_DEBUG_ADDR = None   # eg. "developers@example.com"


# -- End config variables ----------------------------------------------
# (no user serviceable parts after this point)

class Config:
    """Holds all Quixote configuration variables -- see above for
    documentation of them.  The naming convention is simple:
    downcase the above variables to get the names of instance
    attributes of this class.
    """

    config_vars = [
        'error_email',
        'access_log',
        'display_exceptions',
        'error_log',
        'compress_pages',
        'form_tokens',
        'allowed_methods',
        'session_cookie_domain',
        'session_cookie_name',
        'session_cookie_path',
        'session_cookie_secure',
        'session_cookie_httponly',
        'mail_from',
        'mail_server',
        'mail_port',
        'mail_username',
        'mail_password',
        'mail_use_ssl',
        'mail_use_tls',
        'mail_allow_sslv3',
        'mail_debug_addr',
        ]

    def __init__(self, **kwargs):
        self.set_from_dict(globals()) # set defaults
        for name, value in kwargs.items():
            if name not in self.config_vars:
                raise ValueError('unknown config variable %r' % name)
            setattr(self, name, value)

    def set_from_dict(self, config_vars):
        for name, value in config_vars.items():
            if name.isupper():
                name = name.lower()
                if name not in self.config_vars:
                    raise ValueError('unknown config variable %r' % name)
                setattr(self, name, value)

    def read_file(self, filename):
        """Read configuration from a file.  Any variables already
        defined in this Config instance, but not in the file, are
        unchanged, so you can use this to build up a configuration
        by accumulating data from several config files.
        """
        # The config file is Python code -- makes life easy.
        config_vars = {}
        try:
            with open(filename, 'r') as f:
                exec(f.read(), config_vars)
        except IOError as exc:
            if exc.filename is None:    # arg! execfile() loses filename
                exc.filename = filename
            raise exc
        self.set_from_dict(config_vars)
