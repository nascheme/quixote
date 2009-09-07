"""Quixote session management.  There are two levels to Quixote's
session management system:
  - SessionManager
  - Session

A SessionManager is responsible for creating sessions, setting and reading
session cookies, maintaining the collection of all sessions, and so forth.
There is one SessionManager instance per Quixote process.

A Session is the umbrella object for a single session (notionally, a (user,
host, browser_process) triple).  Simple applications can probably get away
with putting all session data into a Session object (or, better, into an
application-specific subclass of Session).

The default implementation provided here is not persistent: when the
Quixote process shuts down, all session data is lost.  See
doc/session-mgmt.txt for information on session persistence.
"""

from time import time, localtime, strftime

from quixote import get_publisher, get_cookie, get_response, get_request, \
     get_session
from quixote.util import randbytes

class NullSessionManager:
    """A session manager that does nothing.  It is the default session manager.
    """

    def start_request(self):
        """
        Called near the beginning of each request: after the HTTPRequest
        object has been built, but before we traverse the URL or call the
        callable object found by URL traversal.
        """

    def finish_successful_request(self):
        """Called near the end of each successful request.  Not called if
        there were any errors processing the request.
        """

    def finish_failed_request(self):
        """Called near the end of a failed request (i.e. a exception that was
        not a PublisherError was raised.
        """


class SessionManager:
    """
    SessionManager acts as a dictionary of all sessions, mapping session
    ID strings to individual session objects.  Session objects are
    instances of Session (or a custom subclass for your application).
    SessionManager is also responsible for creating and destroying
    sessions, for generating and interpreting session cookies, and for
    session persistence (if any -- this implementation is not
    persistent).

    Most applications can just use this class directly; sessions will
    be kept in memory-based dictionaries, and will be lost when the
    Quixote process dies.  Alternatively an application can subclass
    SessionManager to implement specific behaviour, such as persistence.

    Instance attributes:
      session_class : class
        the class that is instantiated to create new session objects
        (in new_session())
      sessions : mapping { session_id:string : Session }
        the collection of sessions managed by this SessionManager
    """

    ACCESS_TIME_RESOLUTION = 1 # in seconds


    def __init__(self, session_class=None, session_mapping=None):
        """(session_class : class = Session, session_mapping : mapping = None)

        Create a new session manager.  There should be one session
        manager per publisher, ie. one per process

        session_class is used by the new_session() method -- it returns
        an instance of session_class.
        """
        self.sessions = {}
        if session_class is None:
            self.session_class = Session
        else:
            self.session_class = session_class
        if session_mapping is None:
            self.sessions = {}
        else:
            self.sessions = session_mapping

    def __repr__(self):
        return "<%s at %x>" % (self.__class__.__name__, id(self))


    # -- Mapping interface ---------------------------------------------
    # (subclasses shouldn't need to override any of this, unless
    # your application passes in a session_mapping object that
    # doesn't provide all of the mapping methods needed here)

    def keys(self):
        """() -> [string]

        Return the list of session IDs of sessions in this session manager.
        """
        return self.sessions.keys()

    def sorted_keys(self):
        """() -> [string]

        Return the same list as keys(), but sorted.
        """
        keys = self.keys()
        keys.sort()
        return keys

    def values(self):
        """() -> [Session]

        Return the list of sessions in this session manager.
        """
        return self.sessions.values()

    def items(self):
        """() -> [(string, Session)]

        Return the list of (session_id, session) pairs in this session
        manager.
        """
        return self.sessions.items()

    def get(self, session_id, default=None):
        """(session_id : string, default : any = None) -> Session

        Return the session object identified by 'session_id', or None if
        no such session.
        """
        return self.sessions.get(session_id, default)

    def __iter__(self):
        return self.sessions.itervalues()

    def __getitem__(self, session_id):
        """(session_id : string) -> Session

        Return the session object identified by 'session_id'.  Raise KeyError
        if no such session.
        """
        return self.sessions[session_id]

    def has_key(self, session_id):
        """(session_id : string) -> boolean

        Return true if a session identified by 'session_id' exists in
        the session manager.
        """
        return session_id in self.sessions

    def __contains__(self, session_id):
        return self.has_key(session_id)

    def has_session(self, session_id):
        return self.has_key(session_id)

    def __setitem__(self, session_id, session):
        """(session_id : string, session : Session)

        Store 'session' in the session manager under 'session_id'.
        """
        if not isinstance(session, self.session_class):
            raise TypeError("session not an instance of %r: %r"
                            % (self.session_class, session))
        assert session.id is not None, "session ID not set"
        assert session_id == session.id, "session ID mismatch"
        self.sessions[session_id] = session

    def __delitem__(self, session_id):
        """(session_id : string) -> Session

        Remove the session object identified by 'session_id' from the session
        manager.  Raise KeyError if no such session.
        """
        del self.sessions[session_id]

    # -- Transactional interface ---------------------------------------
    # Useful for applications that provide a transaction-oriented
    # persistence mechanism.  You'll still need to provide a mapping
    # object that works with your persistence mechanism; these two
    # methods let you hook into your transaction machinery after a
    # request is finished processing.

    def abort_changes(self, session):
        """(session : Session)

        Placeholder for subclasses that implement transactional
        persistence: forget about saving changes to the current
        session.  Called by the publisher when a request fails,
        ie. when it catches an exception other than PublishError.
        """
        pass

    def commit_changes(self, session):
        """(session : Session)

        Placeholder for subclasses that implement transactional
        persistence: commit changes to the current session.  Called by
        the publisher when a request completes successfully, or is
        interrupted by a PublishError exception.
        """
        pass


    # -- Session management --------------------------------------------
    # these build on the storage mechanism implemented by the
    # above mapping methods, and are concerned with all the high-
    # level details of managing web sessions

    def new_session(self, id):
        """(id : string) -> Session

        Return a new session object, ie. an instance of the session_class
        class passed to the constructor (defaults to Session).
        """
        return self.session_class(id)

    def _get_session_id(self, config):
        """() -> string

        Find the ID of the current session by looking for the session
        cookie in the request.  Return None if no such cookie or the
        cookie has been expired, otherwise return the cookie's value.
        """
        id = get_cookie(config.session_cookie_name)
        if id == "" or id == "*del*":
            return None
        else:
            return id

    def _make_session_id(self):
        # Generate a session ID, which is just the value of the session
        # cookie we are about to drop on the user.  (It's also the key
        # used with the session manager mapping interface.)
        id = None
        while id is None or self.has_session(id):
            id = randbytes(8)  # 64-bit random number
        return id

    def _create_session(self):
        # Create a new session object, with no ID for now - one will
        # be assigned later if we save the session.
        return self.new_session(None)

    def get_session(self):
        """() -> Session

        Fetch or create a session object for the current session, and
        return it.  If a session cookie is found in the HTTP request
        object, use it to look up and return an existing session object.
        If no session cookie is found, create a new session.

        Note that this method does *not* cause the new session to be
        stored in the session manager, nor does it drop a session cookie
        on the user.  Those are both the responsibility of
        maintain_session(), called at the end of a request.
        """
        config = get_publisher().config
        id = self._get_session_id(config)
        session = self.get(id) or self._create_session()
        session._set_access_time(self.ACCESS_TIME_RESOLUTION)
        return session

    def maintain_session(self, session):
        """(session : Session)

        Maintain session information.  This method is called after servicing
        an HTTP request, just before the response is returned.  If a session
        contains information it is saved and a cookie dropped on the client.
        If not, the session is discarded and the client will be instructed
        to delete the session cookie (if any).
        """
        if not session.has_info():
            # Session has no useful info -- forget it.  If it previously
            # had useful information and no longer does, we have to
            # explicitly forget it.
            if session.id and self.has_session(session.id):
                del self[session.id]
                self.revoke_session_cookie()
            return

        if session.id is None:
            # This is the first time this session has had useful
            # info -- store it and set the session cookie.
            session.id = self._make_session_id()
            self[session.id] = session
            self.set_session_cookie(session.id)

        elif session.is_dirty():
            # We have already stored this session, but it's dirty
            # and needs to be stored again.  This will never happen
            # with the default Session class, but it's there for
            # applications using a persistence mechanism that requires
            # repeatedly storing the same object in the same mapping.
            self[session.id] = session

    def _set_cookie(self, value, **attrs):
        config = get_publisher().config
        name = config.session_cookie_name
        if config.session_cookie_path:
            path = config.session_cookie_path
        else:
            path = get_request().get_environ('SCRIPT_NAME')
            if not path.endswith("/"):
                path += "/"
        domain = config.session_cookie_domain
        attrs = attrs.copy()
        if config.session_cookie_secure:
            attrs['secure'] = 1
        if config.session_cookie_httponly:
            attrs['httponly'] = 1
        get_response().set_cookie(name, value, domain=domain,
                                  path=path, **attrs)
        return name

    def set_session_cookie(self, session_id):
        """(session_id : string)

        Ensure that a session cookie with value 'session_id' will be
        returned to the client via the response object.
        """
        self._set_cookie(session_id)

    def revoke_session_cookie(self):
        """
        Remove the session cookie from the remote user's session by
        resetting the value and maximum age in the response object.  Also
        remove the cookie from the request so that further processing of
        this request does not see the cookie's revoked value.
        """
        cookie_name = self._set_cookie("", max_age=0)
        if get_cookie(cookie_name) is not None:
            del get_request().cookies[cookie_name]

    def expire_session(self):
        """
        Expire the current session, ie. revoke the session cookie from
        the client and remove the session object from the session
        manager and from the current request.
        """
        self.revoke_session_cookie()
        request = get_request()
        try:
            del self[request.session.id]
        except KeyError:
            # This can happen if the current session hasn't been saved
            # yet, eg. if someone tries to leave a session with no
            # interesting data.  That's not a big deal, so ignore it.
            pass
        request.session = None

    def has_session_cookie(self, must_exist=False):
        """(must_exist : boolean = false) -> bool

        Return true if the request already has a cookie identifying a
        session object.  If 'must_exist' is true, the cookie must
        correspond to a currently existing session; otherwise (the
        default), we just check for the existence of the session cookie
        and don't inspect its content at all.
        """
        config = get_publisher().config
        id = get_cookie(config.session_cookie_name)
        if id is None:
            return False
        if must_exist:
            return self.has_session(id)
        else:
            return True

    # -- Hooks into the Quixote main loop ------------------------------

    def start_request(self):
        """
        Called near the beginning of each request: after the HTTPRequest
        object has been built, but before we traverse the URL or call the
        callable object found by URL traversal.
        """
        session = self.get_session()
        get_request().session = session
        session.start_request()

    def finish_successful_request(self):
        """Called near the end of each successful request.  Not called if
        there were any errors processing the request.
        """
        session = get_session()
        if session is not None:
            self.maintain_session(session)
        self.commit_changes(session)

    def finish_failed_request(self):
        """Called near the end of a failed request (i.e. a exception that was
        not a PublisherError was raised.
        """
        self.abort_changes(get_session())


class Session:
    """
    Holds information about the current session.  The only information
    that is likely to be useful to applications is the 'user' attribute,
    which applications can use as they please.

    Instance attributes:
      id : string
        the session ID (generated by SessionManager and used as the
        value of the session cookie)
      user : any
        an object to identify the human being on the other end of the
        line.  It's up to you whether to store just a string in 'user',
        or some more complex data structure or object.
      _remote_address : string
        IP address of user owning this session (only set when the
        session is created)
      _creation_time : float
      _access_time : float
        two ways of keeping track of the "age" of the session.
        Note that '__access_time' is maintained by the SessionManager that
        owns this session, using _set_access_time().
      _form_tokens : [string]
        outstanding form tokens.  This is used as a queue that can grow
        up to MAX_FORM_TOKENS.  Tokens are removed when forms are submitted.

    Feel free to access 'id' and 'user' directly, but do not modify
    'id'.  The preferred way to set 'user' is with the set_user() method
    (which you might want to override for type-checking).
    """

    MAX_FORM_TOKENS = 16 # maximum number of outstanding form tokens

    def __init__(self, id):
        self.id = id
        self.user = None
        self._remote_address = get_request().get_environ("REMOTE_ADDR")
        self._creation_time = self._access_time = time()
        self._form_tokens = [] # queue

    def __repr__(self):
        return "<%s at %x: %s>" % (self.__class__.__name__, id(self), self.id)

    def __str__(self):
        if self.user:
            return "session %s (user %s)" % (self.id, self.user)
        else:
            return "session %s (no user)" % self.id

    def has_info(self):
        """() -> boolean

        Return true if this session contains any information that must
        be saved.
        """
        return self.user or self._form_tokens

    def is_dirty(self):
        """() -> boolean

        Return true if this session has changed since it was last saved
        such that it needs to be saved again.

        Default implementation always returns false since the default
        storage mechanism is an in-memory dictionary, and you don't have
        to put the same object into the same slot of a dictionary twice.
        If sessions are stored to, eg., files in a directory or slots in
        a hash file, is_dirty() should probably be an alias or wrapper
        for has_info().  See doc/session-mgmt.txt.
        """
        return False

    def dump(self, file=None, header=True, deep=True):
        time_fmt = "%Y-%m-%d %H:%M:%S"
        ctime = strftime(time_fmt, localtime(self._creation_time))
        atime = strftime(time_fmt, localtime(self._access_time))

        if header:
            file.write('session %s:' % self.id)
        file.write('  user %s' % self.user)
        file.write('  _remote_address: %s' % self._remote_address)
        file.write('  created %s, last accessed %s' % (ctime, atime))
        file.write('  _form_tokens: %s\n' % self._form_tokens)

    def start_request(self):
        """
        Called near the beginning of each request: after the HTTPRequest
        object has been built, but before we traverse the URL or call the
        callable object found by URL traversal.
        """
        if self.user is not None:
            get_request().environ['REMOTE_USER'] = str(self.user)

    # -- Simple accessors and modifiers --------------------------------

    def set_user(self, user):
        self.user = user

    def get_user(self):
        return self.user

    def get_remote_address(self):
        """Return the IP address (dotted-quad string) that made the
        initial request in this session.
        """
        return self._remote_address

    def get_creation_time(self):
        """Return the time that this session was created (seconds
        since epoch).
        """
        return self._creation_time

    def get_access_time(self):
        """Return the time that this session was last accessed (seconds
        since epoch).
        """
        return self._access_time

    def get_creation_age(self, _now=None):
        """Return the number of seconds since session was created."""
        # _now arg is not strictly necessary, but there for consistency
        # with get_access_age()
        return (_now or time()) - self._creation_time

    def get_access_age(self, _now=None):
        """Return the number of seconds since session was last accessed."""
        # _now arg is for SessionManager's use
        return (_now or time()) - self._access_time


    # -- Methods for SessionManager only -------------------------------

    def _set_access_time(self, resolution):
        now = time()
        if now - self._access_time > resolution:
            self._access_time = now


    # -- Form token methods --------------------------------------------

    def create_form_token(self):
        """() -> string

        Create a new form token and add it to a queue of outstanding form
        tokens for this session.  A maximum of MAX_FORM_TOKENS are saved.
        The new token is returned.
        """
        token = randbytes(8)
        self._form_tokens.append(token)
        extra = len(self._form_tokens) - self.MAX_FORM_TOKENS
        if extra > 0:
            del self._form_tokens[:extra]
        return token

    def has_form_token(self, token):
        """(token : string) -> boolean

        Return true if 'token' is in the queue of outstanding tokens.
        """
        return token in self._form_tokens

    def remove_form_token(self, token):
        """(token : string)

        Remove 'token' from the queue of outstanding tokens.
        """
        self._form_tokens.remove(token)
