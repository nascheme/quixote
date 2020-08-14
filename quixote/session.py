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
     get_session, get_param
from quixote.util import randbytes, safe_str_cmp


CSRF_TOKEN_NAME = 'csrf_token'


class SessionStore:
    """Component used by SessionManager to save/load/delete transactions
    into some form of storage.
    """
    def load_session(self, id):
        """Return the session if it exists, else return 'None'.
        """
        raise NotImplementedError()

    def save_session(self, session):
        """Save the session in the store.
        """
        raise NotImplementedError()

    def delete_session(self, session_id):
        """Delete the session in the store.
        """
        raise NotImplementedError()

    def has_session(self, id):
        """Return true if the session exists in the store, else false.
        """
        return self.load_session(id) is not None

    def __iter__(self):
        """Return an iterator of all session IDs in the storage.
        """
        raise NotImplementedError()

    def transaction_start(self):
        """Called near the beginning of each request: after the HTTPRequest
        object has been built, but before we traverse the URL or call the
        callable object found by URL traversal.
        """
        pass

    def transaction_commit(self, session):
        """Called near the end of each successful request.  Not called if
        there were any errors processing the request.
        """
        pass

    def transaction_abort(self, session):
        """Called near the end of a failed request (i.e. a exception that was
        not a PublisherError was raised.
        """
        pass


class BaseSessionManager:
    """This base class contains the essential methods that a Quixote
    session manager must implement.
    """

    # use a class attribute in case __init__ not called on subclass
    store = SessionStore()

    def __init__(self, session_class=None, session_store=None):
        self.session_class = session_class or Session
        if session_store is not None:
            self.store = session_store

    # Hooks into the Quixote main loop.  These are the only three
    # methods that a session manager *must* implement.

    def start_request(self):
        """
        Called near the beginning of each request: after the HTTPRequest
        object has been built, but before we traverse the URL or call the
        callable object found by URL traversal.
        """
        self.store.transaction_start()
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

    # Methods used to add/update/delete and find sessions.  For sessions
    # stored in databases, these methods must transfer data to and from
    # the database.

    def __iter__(self):
        """Iterate over all the sessions contained by the manager and return
        each Session object.
        """
        for session_id in self.store:
            yield self.store.load_session(session_id)

    def get(self, session_id):
        """(session_id) -> Session|None

        Return the session object identified by 'session_id'.  Return None if
        there is no such session.
        """
        return self.store.load_session(session_id)

    def __setitem__(self, session_id, session):
        """Store a new or updated session object into the session manager.
        """
        return self.store.save_session(session)

    def __delitem__(self, session_id):
        """Remove a session from the session manager.  E.g. if the user
        signs out or the session expires.
        """
        return self.store.delete_session(session_id)

    def __contains__(self, session_id):
        """(session_id : string) -> boolean

        Return true if a session identified by 'session_id' exists in
        the session manager.
        """
        return self.store.has_session(session_id)

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
        self.store.transaction_abort(session)

    def commit_changes(self, session):
        """(session : Session)

        Placeholder for subclasses that implement transactional
        persistence: commit changes to the current session.  Called by
        the publisher when a request completes successfully, or is
        interrupted by a PublishError exception.
        """
        self.store.transaction_commit(session)


    # Below are methods to implement the three Quixote main loop hooks above.
    # Other session manager implementions may re-use these or do their own
    # thing.

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
        session = self.get(id)
        if session is None:
            session = self.new_session(None)
        session._set_access_time(self.ACCESS_TIME_RESOLUTION)
        return session

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
        while id is None or id in self:
            id = randbytes(16)  # 128-bit random number
        return id

    def new_session(self, id):
        """(id : string) -> Session

        Return a new session object, ie. an instance of the session_class
        class passed to the constructor (defaults to Session).
        """
        return self.session_class(id)

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
            if session.id and session.id in self:
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

    def set_session_cookie(self, session_id, **attrs):
        set_session_cookie(session_id, **attrs)

    def revoke_session_cookie(self):
        """
        Remove the session cookie from the remote user's session by
        resetting the value and maximum age in the response object.  Also
        remove the cookie from the request so that further processing of
        this request does not see the cookie's revoked value.
        """
        cookie_name = self.set_session_cookie("", max_age=0)
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



class NullSessionManager(BaseSessionManager):
    """A session manager that does nothing.  It is the default session
    manager.
    """

    def start_request(self):
        pass

    def finish_successful_request(self):
        pass

    def finish_failed_request(self):
        pass

    def __iter__(self):
        return iter([])

    def get(self, session_id):
        return None


class SessionManager(BaseSessionManager):
    """
    This is a session manager that uses a dictionary to store sessions.
    Session objects are instances of Session (or a custom subclass for your
    application).  SessionManager is also responsible for creating and
    destroying sessions, for generating and interpreting session cookies, and
    for session persistence (if any -- this implementation is not persistent).

    Most applications can just use this class directly; sessions will
    be kept in memory-based dictionaries, and will be lost when the
    Quixote process dies.  Alternatively an application can subclass
    BaseSessionManager to implement specific behaviour, such as persistence.

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
        BaseSessionManager.__init__(self, session_class=session_class)
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

    # Implementation of the required methods of the session manager.

    def get(self, session_id, default=None):
        """(session_id : string, default : any = None) -> Session

        Return the session object identified by 'session_id', or None if
        no such session.
        """
        return self.sessions.get(session_id, default)

    def __iter__(self):
        return iter(self.sessions.values())

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

    def __contains__(self, session_id):
        """(session_id : string) -> boolean

        Return true if a session identified by 'session_id' exists in
        the session manager.
        """
        return session_id in self.sessions

    # The methods that follow are retained for backwards compatibility with
    # older Quixote applications.  Most of them just provide a more complete
    # mapping interface for SessionManager but nothing in Quixote expects them
    # to exist.

    def __getitem__(self, session_id):
        """(session_id : string) -> Session

        Return the session object identified by 'session_id'.  Raise KeyError
        if there is no such session.
        """
        return self.sessions[session_id]

    def has_session(self, session_id):
        return session_id in self.sessions

    def keys(self):
        """() -> [string]

        Return the list of session IDs of sessions in this session manager.
        """
        return list(self.sessions.keys())

    def sorted_keys(self):
        """() -> [string]

        Return the same list as keys(), but sorted.
        """
        return sorted(self.keys())

    def values(self):
        """() -> [Session]

        Return the list of sessions in this session manager.
        """
        return list(self.sessions.values())

    def items(self):
        """() -> [(string, Session)]

        Return the list of (session_id, session) pairs in this session
        manager.
        """
        return list(self.sessions.items())

    def _create_session(self):
        # Create a new session object, with no ID for now - one will
        # be assigned later if we save the session.
        return self.new_session(None)

    def _set_cookie(self, value, **attrs):
        # exists only for backwards compatiblity, use set_session_cookie()
        set_session_cookie(value, **attrs)

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
      _csrf_token  : string|None
        a CSRF prevention token stored for the session.  It is generated
        by get_csrf_token().  It can be checked using valid_csrf_token().

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
        self._csrf_token = None

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
        return bool(self.user or self._form_tokens or self._csrf_token)

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
        token = randbytes(16)
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

    # -- Cross-site request forgery (CSRF) prevention tokens -----------

    def get_csrf_token(self):
        """Return a random token unique to the session.  This is
        suitable for inclusion in forms as a hidden field in order
        to prevent CSRF attacks.  When the form is submitted, the
        token must be checked using a constant time compare.  The
        token should not be included in GET URLs as there is a
        greater risk of disclosure.  Using a separate token provides
        some security benefits over re-using the session ID as a
        CSRF token.
        """
        if self._csrf_token is None:
            self._csrf_token = randbytes(16) # 128-bit random number
        return self._csrf_token

    def valid_csrf_token(self, name=None):
        """Return true if the request contains the CSRF token in the
        parameter called 'name'.  The HTTP method must be POST.  If
        'name' is not provided, then CSRF_TOKEN_NAME is used as the
        name.
        """
        if get_request().get_method() != 'POST':
            return False
        value = get_param(name or CSRF_TOKEN_NAME, None)
        if not value:
            return False
        return safe_str_cmp(value, self.get_csrf_token())


def set_session_cookie(session_id, **attrs):
    """Create a cookie in the HTTP response for 'session_id'.
    """
    config = get_publisher().config
    name = config.session_cookie_name
    if config.session_cookie_path:
        path = config.session_cookie_path
    else:
        path = get_request().get_environ('SCRIPT_NAME')
        if not path.endswith('/'):
            path += '/'
    domain = config.session_cookie_domain
    attrs = attrs.copy()
    if config.session_cookie_secure:
        attrs['secure'] = 1
    if config.session_cookie_httponly:
        attrs['httponly'] = 1
    get_response().set_cookie(name, session_id, domain=domain, path=path,
                              **attrs)
    return name
