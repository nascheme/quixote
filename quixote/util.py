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
import io
import base64
import mimetypes
import urllib.request, urllib.parse, urllib.error
import xmlrpc.server as _xmlrpc
from email.utils import formatdate

try:
    import secrets
except ImportError:
    secrets = None

import quixote
from quixote import errors
from quixote.directory import Directory
from quixote.html import htmltext, TemplateIO
from quixote.http_response import Stream

if secrets is not None:
    # available in Python 3.6+, this is the preferred implementation
    randbytes = secrets.token_urlsafe
elif hasattr(os, 'urandom'):
    # available in Python 2.4 and also works on win32
    def _encode_base64(s):
        return base64.urlsafe_b64encode(s).rstrip(b'=\n').decode('ascii')

    def randbytes(n=16):
        """Return bytes of random data as a text string."""
        return _encode_base64(os.urandom(n))


else:
    # give up, we used to try to provide a less secure version
    def randbytes(n=16):
        raise NotImplementedError('platform missing os.urandom')


def safe_str_cmp(a, b):
    """A (mostly) constant time comparison function for two strings.
    Returns True if the strings are equal.  Using a constant time
    function is necessary to prevent timing attacks with checking
    security tokens (e.g. passwords, form tokens).  The arguments
    can 'str' or 'bytes' object but mixed types are not allowed.
    """
    if not isinstance(a, bytes):
        a = a.encode('utf-8')
        b = b.encode('utf-8')
    result = 0 if len(a) == len(b) else 1
    for x, y in zip(a, b):
        result |= x ^ y
    return result == 0


def import_object(name):
    i = name.rfind('.')
    if i != -1:
        module_name = name[:i]
        object_name = name[i + 1 :]
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
    params, method = _xmlrpc.loads(data)

    try:
        result = func(method, params)
    except _xmlrpc.Fault as exc:
        result = exc
    except BaseException:
        # report exception back to client
        result = _xmlrpc.dumps(
            _xmlrpc.Fault(1, "%s:%s" % (sys.exc_info()[0], sys.exc_info()[1]))
        )
    else:
        result = (result,)
        result = _xmlrpc.dumps(result, methodresponse=1)

    request.response.set_content_type('text/xml')
    return result


class FileStream(Stream):

    CHUNK_SIZE = 20000

    def __init__(self, fp, size=None):
        self.fp = fp
        self.length = size

    def __iter__(self):
        return self

    def __next__(self):
        chunk = self.fp.read(self.CHUNK_SIZE)
        if not chunk:
            raise StopIteration
        return chunk

    def close(self):
        if hasattr(self.fp, 'close'):
            self.fp.close()


class StaticFile:

    """
    Wrapper for a static file on the filesystem.
    """

    def __init__(
        self,
        path,
        follow_symlinks=False,
        mime_type=None,
        encoding=None,
        cache_time=None,
    ):
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
            raise ValueError("Path %r is not absolute" % path)
        # Decide the Content-Type of the file
        guess_mime, guess_enc = mimetypes.guess_type(
            os.path.basename(path), strict=False
        )
        self.mime_type = mime_type or guess_mime or 'text/plain'
        self.encoding = encoding or guess_enc or None
        self.cache_time = cache_time
        self.follow_symlinks = follow_symlinks

    def __call__(self):
        if not self.follow_symlinks and os.path.islink(self.path):
            raise errors.TraversalError(
                private_msg="Path %r is a symlink" % self.path
            )
        request = quixote.get_request()
        response = quixote.get_response()

        if self.cache_time is None:
            response.set_expires(None)  # don't set the Expires header
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
        last_modified = formatdate(stat.st_mtime, usegmt=True)
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

    def __init__(
        self,
        path,
        use_cache=False,
        list_directory=False,
        follow_symlinks=False,
        cache_time=None,
        file_class=None,
        index_filenames=None,
    ):
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
            raise ValueError("Path %r is not absolute" % path)

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
                if not isinstance(obj, StaticDirectory) and callable(obj):
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
                r += template % (
                    urllib.parse.quote(filename),
                    filename,
                    marker,
                )
            r += htmltext('</pre>')
            body = r.getvalue()
        else:
            title = 'Directory listing denied'
            body = htmltext(
                '<p>This directory does not allow its contents '
                'to be listed.</p>'
            )
        return errors.format_page(title, body)

    def _q_lookup(self, name):
        """
        Get a file from the filesystem directory and return the StaticFile
        or StaticDirectory wrapper of it; use caching if that is in use.
        """
        if name in ('.', '..'):
            raise errors.TraversalError(
                private_msg="Attempt to use '.', '..'"
            )
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
                item = self.__class__(
                    item_filepath,
                    self.use_cache,
                    self.list_directory,
                    self.follow_symlinks,
                    self.cache_time,
                    self.file_class,
                    self.index_filenames,
                )

            elif os.path.isfile(item_filepath):
                item = self.file_class(
                    item_filepath,
                    self.follow_symlinks,
                    cache_time=self.cache_time,
                )
            else:
                raise errors.TraversalError
            if self.use_cache:
                self.cache[name] = item
        return item


class MemoryFile:
    """A static-like file that exists only in memory, not on disk.  The
    data for the file is stored as a 'str' object.
    """

    def __init__(self, data, mime_type=None, encoding=None, cache_time=None):
        self.data = data
        self.mime_type = mime_type or 'text/plain'
        self.encoding = encoding or quixote.DEFAULT_CHARSET
        self.cache_time = cache_time

    def __call__(self):
        response = quixote.get_response()
        response.set_content_type(self.mime_type, self.encoding)
        if self.cache_time:
            response.set_expires(seconds=self.cache_time)
        return self.data


class StaticBundle(Directory):
    """A virtual directory that holds static files.  Can be used for
    Javascript, CSS files, and images.  It can optionally concatenate
    multiple text files into a single file (e.g. Javascript).  The modification
    time of the file is used as part of the URL and so a very long cache time
    can be specified.  If the file gets updated, a new path will be generated
    by make_path() because of the new modification time.
    """

    # Because we generate a path based on the modification time of the file
    # it is safe to use a very long cache time.
    CACHE_TIME = 3600 * 24 * 100

    def __init__(self, dirname, basepath='', sep='\n', encoding=None):
        """Create a new StaticBundle.  'dirname' is a file path to the
        files on disk.  'basepath' is the base web path for the files and
        is used by make_path() to generate an absolute path URL.  If files
        are to be concatenated, 'sep' is used as a separator between files.
        Using newline is the default since minimized Javascript and CSS
        sometimes are missing a final newline.
        """
        self.basedir = dirname
        self.basepath = basepath
        self.sep = sep
        self.encoding = encoding or quixote.DEFAULT_CHARSET
        self.files = {}
        self.paths = {}

    def make_path(self, *filenames):
        """Generate a path for a file or list of files.  The returned path
        will include the modification time as a component.  If multiple file
        names are provided, they must all have the same extension.
        """
        filenames = [str(fn) for fn in filenames]
        key = ','.join(filenames)
        path = self.paths.get(key)
        if path is not None:
            return path
        exts = set([os.path.splitext(fn)[1] for fn in filenames])
        if len(exts) != 1:
            raise ValueError('different file extensions %s' % exts)
        mtimes = []
        for fn in filenames:
            fn = os.path.join(self.basedir, fn)
            if not os.path.exists(fn):
                raise ValueError('missing file %r' % fn)
            st = os.stat(fn)
            mtimes.append(int(st.st_mtime))
        path = '%s/%s/%s' % (self.basepath, max(mtimes), key)
        self.paths[key] = path
        return path

    def _read_static_data(self, filenames):
        """Generate concatenated data for 'filenames'.  Return the data as a
        'str' and the guessed MIME type (based on file extension).
        """
        data = io.StringIO()
        mime_type = None
        for fn in filenames:
            if fn == '..' or '/' in fn:
                # should not happen, check anyhow
                raise ValueError('invalid file name for static file')
            filename = os.path.join(self.basedir, fn)
            if not os.path.isfile(filename):
                raise errors.TraversalError('static file missing')
            with open(filename, 'r', encoding=self.encoding) as fp:
                data.write(fp.read())
            if fn is not filenames[-1]:
                data.write(self.sep)
            if mime_type is None:
                mime_type, guess_enc = mimetypes.guess_type(fn, strict=False)
        return data.getvalue(), mime_type

    def _q_traverse(self, path):
        if len(path) == 1:
            # if mtime component missing, allow direct path, no caching
            filename = path[0]
            cache_time = None
        elif len(path) == 2:
            # path with a modification time prefix, mtime is not checked
            filename = path[1]
            if filename == '..':
                raise errors.TraversalError('invalid static file path')
            try:
                mtime = int(path[0])  # noqa: F841
            except ValueError:
                raise errors.TraversalError('invalid mtime for static file')
            cache_time = self.CACHE_TIME
        else:
            raise errors.TraversalError()
        if filename not in self.files:
            # A file we haven't been asked for yet.  Create a StaticFile
            # wrapper for it.
            if ',' in filename:
                # it is a virtual file created by concatenating text files
                filenames = filename.split(',')
                data, mime_type = self._read_static_data(filenames)
                static_file = MemoryFile(
                    data,
                    mime_type=mime_type,
                    encoding=self.encoding,
                    cache_time=cache_time,
                )
            else:
                # it is a single static file
                static_file = StaticFile(
                    os.path.join(self.basedir, filename),
                    encoding=self.encoding,
                    cache_time=cache_time,
                )
            self.files[filename] = static_file
        # We have the file wrapper created and ready, call it to return the
        # reponse data.
        return self.files[filename]()


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
    r += htmltext('<h3>form</h3>' '<table>')
    for k, v in request.form.items():
        r += row_fmt % (k, v)
    r += htmltext('</table>' '<h3>cookies</h3>' '<table>')
    for k, v in request.cookies.items():
        r += row_fmt % (k, v)
    r += htmltext('</table>' '<h3>environ</h3>' '<table>')
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
