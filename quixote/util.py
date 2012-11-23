"""quixote.util

Contains various useful functions and classes:

  xmlrpc(request, func) : Processes the body of an XML-RPC request, and calls
                          'func' with the method name and parameters.
  StaticFile            : Wraps a file from a filesystem as a
                          Quixote resource.
  StaticDirectory       : Wraps a directory containing static files as
                          a Quixote directory.

StaticFile and StaticDirectory were contributed by Hamish Lawson.
See doc/static-files.txt for examples of their use.
"""

import sys
import os
import time
import binascii
import mimetypes
import urllib
import xmlrpclib
from rfc822 import formatdate
import quixote
from quixote import errors
from quixote.directory import Directory
from quixote.html import htmltext, TemplateIO
from quixote.http_response import Stream

if hasattr(os, 'urandom'):
    # available in Python 2.4 and also works on win32
    def randbytes(bytes):
        """Return bits of random data as a hex string."""
        return binascii.hexlify(os.urandom(bytes))

elif os.path.exists('/dev/urandom'):
    # /dev/urandom is just as good as /dev/random for cookies (assuming
    # SHA-1 is secure) and it never blocks.
    def randbytes(bytes):
        """Return bits of random data as a hex string."""
        return binascii.hexlify(open("/dev/urandom").read(bytes))

else:
    # this is much less secure than the above function
    import sha
    class _PRNG:
        def __init__(self):
            self.state = sha.new(str(time.time() + time.clock()))
            self.count = 0

        def _get_bytes(self):
            self.state.update('%s %d' % (time.time() + time.clock(),
                                         self.count))
            self.count += 1
            return self.state.hexdigest()

        def randbytes(self, bytes):
            """Return bits of random data as a hex string."""
            s = ""
            chars = 2*bytes
            while len(s) < chars:
                s += self._get_bytes()
            return s[:chars]

    randbytes = _PRNG().randbytes


def import_object(name):
    i = name.rfind('.')
    if i != -1:
        module_name = name[:i]
        object_name = name[i+1:]
        __import__(module_name)
        return getattr(sys.modules[module_name], object_name)
    else:
        __import__(name)
        return sys.modules[name]

def xmlrpc(request, func):
    """xmlrpc(request:Request, func:callable) : string

    Processes the body of an XML-RPC request, and calls 'func' with
    two arguments, a string containing the method name and a tuple of
    parameters.
    """

    # Get contents of POST body
    if request.get_method() != 'POST':
        request.response.set_status(405, "Only the POST method is accepted")
        return "XML-RPC handlers only accept the POST method."

    length = int(request.environ['CONTENT_LENGTH'])
    data = request.stdin.read(length)

    # Parse arguments
    params, method = xmlrpclib.loads(data)

    try:
        result = func(method, params)
    except xmlrpclib.Fault, exc:
        result = exc
    except:
        # report exception back to client
        result = xmlrpclib.dumps(
            xmlrpclib.Fault(1, "%s:%s" % (sys.exc_type, sys.exc_value))
            )
    else:
        result = (result,)
        result = xmlrpclib.dumps(result, methodresponse=1)

    request.response.set_content_type('text/xml')
    return result


class FileStream(Stream):

    CHUNK_SIZE = 20000

    def __init__(self, fp, size=None):
        self.fp = fp
        self.length = size

    def __iter__(self):
        return self

    def next(self):
        chunk = self.fp.read(self.CHUNK_SIZE)
        if not chunk:
            raise StopIteration
        return chunk


class StaticFile:

    """
    Wrapper for a static file on the filesystem.
    """

    def __init__(self, path, follow_symlinks=False,
                 mime_type=None, encoding=None, cache_time=None):
        """StaticFile(path:string, follow_symlinks:bool)

        Initialize instance with the absolute path to the file.  If
        'follow_symlinks' is true, symbolic links will be followed.
        'mime_type' specifies the MIME type, and 'encoding' the
        encoding; if omitted, the MIME type will be guessed,
        defaulting to text/plain.

        Optional cache_time parameter indicates the number of
        seconds a response is considered to be valid, and will
        be used to set the Expires header in the response when
        quixote gets to that part.  If the value is None then
        the Expires header will not be set.
        """

        # Check that the supplied path is absolute and (if a symbolic link) may
        # be followed
        self.path = path
        if not os.path.isabs(path):
            raise ValueError, "Path %r is not absolute" % path
        # Decide the Content-Type of the file
        guess_mime, guess_enc = mimetypes.guess_type(os.path.basename(path),
                                                     strict=False)
        self.mime_type = mime_type or guess_mime or 'text/plain'
        self.encoding = encoding or guess_enc or None
        self.cache_time = cache_time
        self.follow_symlinks = follow_symlinks

    def __call__(self):
        if not self.follow_symlinks and os.path.islink(self.path):
            raise errors.TraversalError(private_msg="Path %r is a symlink"
                                        % self.path)
        request = quixote.get_request()
        response = quixote.get_response()

        if self.cache_time is None:
            response.set_expires(None) # don't set the Expires header
        else:
            # explicitly allow client to cache page by setting the Expires
            # header, this is even more efficient than the using
            # Last-Modified/If-Modified-Since since the browser does not need
            # to contact the server
            response.set_expires(seconds=self.cache_time)

        try:
            stat = os.stat(self.path)
        except OSError:
            raise errors.TraversalError
        last_modified = formatdate(stat.st_mtime)
        if last_modified == request.get_header('If-Modified-Since'):
            # handle exact match of If-Modified-Since header
            response.set_status(304)
            return ''

        # Set the Content-Type for the response and return the file's contents.
        response.set_content_type(self.mime_type)
        if self.encoding:
            response.set_header("Content-Encoding", self.encoding)

        response.set_header('Last-Modified', last_modified)

        return FileStream(open(self.path, 'rb'), stat.st_size)


class StaticDirectory(Directory):

    """
    Wrap a filesystem directory containing static files as a Quixote directory.
    """

    _q_exports = ['']

    FILE_CLASS = StaticFile

    def __init__(self, path, use_cache=False, list_directory=False,
                 follow_symlinks=False, cache_time=None, file_class=None,
                 index_filenames=None):
        """(path:string, use_cache:bool, list_directory:bool,
            follow_symlinks:bool, cache_time:int,
            file_class=None, index_filenames:[string])

        Initialize instance with the absolute path to the file.
        If 'use_cache' is true, StaticFile instances will be cached in memory.
        If 'list_directory' is true, users can request a directory listing.
        If 'follow_symlinks' is true, symbolic links will be followed.

        Optional parameter cache_time allows setting of Expires header in
        response object (see note for StaticFile for more detail).

        Optional parameter 'index_filenames' specifies a list of
        filenames to be used as index files in the directory. First
        file found searching left to right is returned.
        """

        # Check that the supplied path is absolute
        self.path = path
        if not os.path.isabs(path):
            raise ValueError, "Path %r is not absolute" % path

        self.use_cache = use_cache
        self.cache = {}
        self.list_directory = list_directory
        self.follow_symlinks = follow_symlinks
        self.cache_time = cache_time
        if file_class is not None:
            self.file_class = file_class
        else:
            self.file_class = self.FILE_CLASS
        self.index_filenames = index_filenames

    def _q_index(self):
        """
        If directory listings are allowed, generate a simple HTML
        listing of the directory's contents with each item hyperlinked;
        if the item is a subdirectory, place a '/' after it. If not allowed,
        return a page to that effect.
        """
        if self.index_filenames:
            for name in self.index_filenames:
                try:
                    obj = self._q_lookup(name)
                except errors.TraversalError:
                    continue
                if (not isinstance(obj, StaticDirectory)
                        and hasattr(obj, '__call__')):
                    return obj()
        if self.list_directory:
            title = 'Index of %s' % quixote.get_path()
            r = TemplateIO(html=True)
            template = htmltext('<a href="%s">%s</a>%s\n')
            r += htmltext('<pre>')
            r += template % ('..', '..', '')
            files = os.listdir(self.path)
            files.sort()
            for filename in files:
                filepath = os.path.join(self.path, filename)
                marker = os.path.isdir(filepath) and "/" or ""
                r += template % (urllib.quote(filename), filename, marker)
            r += htmltext('</pre>')
            body = r.getvalue()
        else:
            title = 'Directory listing denied'
            body = htmltext('<p>This directory does not allow its contents '
                            'to be listed.</p>')
        return errors.format_page(title, body)

    def _q_lookup(self, name):
        """
        Get a file from the filesystem directory and return the StaticFile
        or StaticDirectory wrapper of it; use caching if that is in use.
        """
        if name in ('.', '..'):
            raise errors.TraversalError(private_msg="Attempt to use '.', '..'")
        if name in self.cache:
            # Get item from cache
            item = self.cache[name]
        else:
            # Get item from filesystem; cache it if caching is in use.
            item_filepath = os.path.join(self.path, name)
            while os.path.islink(item_filepath):
                if not self.follow_symlinks:
                    raise errors.TraversalError
                else:
                    dest = os.readlink(item_filepath)
                    item_filepath = os.path.join(self.path, dest)

            if os.path.isdir(item_filepath):
                item = self.__class__(item_filepath, self.use_cache,
                                      self.list_directory,
                                      self.follow_symlinks, self.cache_time,
                                      self.file_class, self.index_filenames)

            elif os.path.isfile(item_filepath):
                item = self.file_class(item_filepath, self.follow_symlinks,
                                       cache_time=self.cache_time)
            else:
                raise errors.TraversalError
            if self.use_cache:
                self.cache[name] = item
        return item


class Redirector:
    """
    A simple class that can be used from inside _q_lookup() to redirect
    requests.
    """

    _q_exports = []

    def __init__(self, location, permanent=False):
        self.location = location
        self.permanent = permanent

    def _q_lookup(self, component):
        return self

    def __call__(self):
        return quixote.redirect(self.location, self.permanent)


def dump_request(request=None):
    if request is None:
        request = quixote.get_request()
    """Dump an HTTPRequest object as HTML."""
    row_fmt = htmltext('<tr><th>%s</th><td>%s</td></tr>')
    r = TemplateIO(html=True)
    r += htmltext('<h3>form</h3>'
                  '<table>')
    for k, v in request.form.items():
        r += row_fmt % (k, v)
    r += htmltext('</table>'
                  '<h3>cookies</h3>'
                  '<table>')
    for k, v in request.cookies.items():
        r += row_fmt % (k, v)
    r += htmltext('</table>'
                  '<h3>environ</h3>'
                  '<table>')
    for k, v in request.environ.items():
        r += row_fmt % (k, v)
    r += htmltext('</table>')
    return r.getvalue()

def get_directory_path():
    """() -> [object]
    Return the list of traversed instances.
    """
    path = []
    frame = sys._getframe()
    while frame:
        if frame.f_code.co_name == '_q_traverse':
            self = frame.f_locals.get('self', None)
            if path[:1] != [self]:
                path.insert(0, self)
        frame = frame.f_back
    return path
