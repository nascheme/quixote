#!/usr/bin/env python3
"""An alternative Quixote demo.  This version is contained in a single module
and does not use PTL.  The easiest way to run this demo is to use the
simple HTTP server included with Quixote.  For example:

    $ python3 -m quixote run --app quixote.demo.altdemo

The server listens on localhost:8080 by default.  Debug and error output
will be sent to the terminal.

If you have installed durus, you can run the same demo, except with
persistent sessions stored in a durus database, by running:

    $ python3 -m quixote run --app quixote.demo.altdemo --factory create_durus_publisher

"""

from quixote import get_user, get_session, get_session_manager, get_field
from quixote.directory import Directory
from quixote.html import href, htmltext
from quixote.publish import Publisher
from quixote.session import Session, SessionManager
from quixote.util import dump_request

def format_page(title, content):
    request = htmltext(
        '<div style="font-size: smaller;background:#eee">'
        '<h1>Request:</h1>%s</div>') % dump_request()
    return htmltext(
        '<html><head><title>%(title)s</title>'
        '<style type="text/css">\n'
        'body { border: thick solid green; padding: 2em; }\n'
        'h1 { font-size: larger; }\n'
        'th { background: #aaa; text-align:left; font-size: smaller; }\n'
        'td { background: #ccc; font-size: smaller; }\n'
        '</style>'
        '</head><body>%(content)s%(request)s</body></html>') % locals()

def format_request():
    return format_page('Request', dump_request())

def format_link_list(targets):
    return htmltext('<ul>%s</ul>') % htmltext('').join([
        htmltext('<li>%s</li>') % href(target, target) for target in targets])

class RootDirectory(Directory):

    _q_exports = ['', 'login', 'logout']

    def _q_index(self):
        content = htmltext('')
        if not get_user():
            content += htmltext('<p>%s</p>' % href('login', 'login'))
        else:
            content += htmltext(
                '<p>Hello, %s.</p>') % get_user()
            content += htmltext('<p>%s</p>' % href('logout', 'logout'))
        sessions = sorted([(s.id, s) for s in get_session_manager()])
        if sessions:
            content += htmltext('<table><tr>'
                                '<th></th>'
                                '<th>Session</th>'
                                '<th>User</th>'
                                '<th>Number of Requests</th>'
                                '</tr>')
            this_session = get_session()
            for index, (id, session) in enumerate(sessions):
                if session is this_session:
                    formatted_id = htmltext(
                        '<span style="font-weight:bold">%s</span>' % id)
                else:
                    formatted_id = id
                content += htmltext(
                    '<tr><td>%s</td><td>%s</td><td>%s</td><td>%d</td>' % (
                    index,
                    formatted_id,
                    session.user or htmltext("<em>None</em>"),
                    session.num_requests))
            content += htmltext('</table>')
        return format_page("Quixote Session Management Demo", content)

    def login(self):
        content = htmltext('')
        if get_field("name"):
            session = get_session()
            session.set_user(get_field("name")) # This is the important part.
            content += htmltext(
                '<p>Welcome, %s!  Thank you for logging in.</p>') % get_user()
            content += href("..", "go back")
        else:
            content += htmltext(
                '<p>Please enter your name here:</p>\n'
                '<form method="POST" action="login">'
                '<input name="name" />'
                '<input type="submit" />'
                '</form>')
        return format_page("Quixote Session Demo: Login", content)

    def logout(self):
        if get_user():
            content = htmltext('<p>Goodbye, %s.</p>') % get_user()
        else:
            content = htmltext('<p>That would be redundant.</p>')
        content += href("..", "start over")
        get_session_manager().expire_session() # This is the important part.
        return format_page("Quixote Session Demo: Logout", content)


class DemoSession(Session):

    def __init__(self, id):
        Session.__init__(self, id)
        self.num_requests = 0

    def start_request(self):
        """
        This is called from the main object publishing loop whenever
        we start processing a new request.  Obviously, this is a good
        place to track the number of requests made.  (If we were
        interested in the number of *successful* requests made, then
        we could override finish_request(), which is called by
        the publisher at the end of each successful request.)
        """
        Session.start_request(self)
        self.num_requests += 1

    def has_info(self):
        """
        Overriding has_info() is essential but non-obvious.  The
        session manager uses has_info() to know if it should hang on
        to a session object or not: if a session is "dirty", then it
        must be saved.  This prevents saving sessions that don't need
        to be saved, which is especially important as a defensive
        measure against clients that don't handle cookies: without it,
        we might create and store a new session object for every
        request made by such clients.  With has_info(), we create the
        new session object every time, but throw it away unsaved as
        soon as the request is complete.

        (Of course, if you write your session class such that
        has_info() always returns true after a request has been
        processed, you're back to the original problem -- and in fact,
        this class *has* been written that way, because num_requests
        is incremented on every request, which makes has_info() return
        true, which makes SessionManager always store the session
        object.  In a real application, think carefully before putting
        data in a session object that causes has_info() to return
        true.)
        """
        return (self.num_requests > 0) or Session.has_info(self)

    is_dirty = has_info


def create_publisher():
    return Publisher(RootDirectory(),
                     session_manager=SessionManager(session_class=DemoSession),
                     display_exceptions='plain')

try:
    # If durus is installed, define a create_durus_publisher() that
    # uses a durus database to store persistent sessions.
    import os, tempfile
    from durus.persistent import Persistent
    from durus.persistent_dict import PersistentDict
    from durus.file_storage import FileStorage
    from durus.connection import Connection
    connection = None # set in create_durus_publisher()

    class PersistentSession(DemoSession, Persistent):
        pass

    class PersistentSessionManager(SessionManager, Persistent):
        def __init__(self):
            sessions = PersistentDict()
            SessionManager.__init__(self,
                                    session_class=PersistentSession,
                                    session_mapping=sessions)
        def forget_changes(self, session):
            print('abort changes', get_session())
            connection.abort()

        def commit_changes(self, session):
            print('commit changes', get_session())
            connection.commit()

    def create_durus_publisher():
        global connection
        filename = os.path.join(tempfile.gettempdir(), 'quixote-demo.durus')
        print('Opening %r as a Durus database.' % filename)
        connection = Connection(FileStorage(filename))
        root = connection.get_root()
        session_manager = root.get('session_manager', None)
        if session_manager is None:
            session_manager = PersistentSessionManager()
            connection.get_root()['session_manager'] = session_manager
            connection.commit()
        return Publisher(RootDirectory(),
                         session_manager=session_manager,
                         display_exceptions='plain')
except ImportError:
    pass # durus not installed.
