"""Assorted helpers, mainly for serving static files.

Static content.  Place one of these in a `Directory` to serve files:

  * `StaticFile` -- serve a single file from the filesystem.
  * `StaticDirectory` -- serve a whole filesystem tree.
  * `StaticBundle` -- serve CSS/JS/image assets with content-hash URLs
    (via `StaticBundle.make_path`) so they can be cached for a long time.
  * `FileStream` -- a `Stream` over an open file, for streaming a download
    without loading it all into memory.

Other helpers include `xmlrpc` (dispatch an XML-RPC request body),
`get_directory_path` (the current traversal stack, for breadcrumbs),
`safe_str_cmp` (mostly constant-time compare), and `randbytes`.

StaticFile and StaticDirectory were contributed by Hamish Lawson.
See doc/static-files.txt for examples of their use.
"""

from __future__ import annotations

import base64
import functools
import hashlib
import io
import mimetypes
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
import xmlrpc.client as _xmlrpc
from collections.abc import Callable, Sequence
from email.utils import formatdate
from typing import IO, TYPE_CHECKING, Any, cast

try:
    import secrets
except ImportError:
    secrets = None

import quixote
from quixote import errors
from quixote.directory import Directory
from quixote.html import TemplateIO, htmltext
from quixote.http_response import Stream

if TYPE_CHECKING:
    from quixote.http_request import HTTPRequest

type FilePath = str | os.PathLike[str]
type StaticResult = str | FileStream
type StaticItem = StaticFile | StaticDirectory


if secrets is not None:
    # available in Python 3.6+, this is the preferred implementation
    def randbytes(n: int = 16) -> str:
        """Return bytes of random data as a text string."""
        return secrets.token_urlsafe(n)

elif hasattr(os, 'urandom'):
    # available in Python 2.4 and also works on win32
    def _encode_base64(s: bytes) -> str:
        return base64.urlsafe_b64encode(s).rstrip(b'=\n').decode('ascii')

    def randbytes(n: int = 16) -> str:
        """Return bytes of random data as a text string."""
        return _encode_base64(os.urandom(n))

else:
    # give up, we used to try to provide a less secure version
    def randbytes(n: int = 16) -> str:
        raise NotImplementedError('platform missing os.urandom')


def safe_str_cmp(a: str | bytes, b: str | bytes) -> bool:
    """Compare two strings while reducing content-based timing leaks.

    Returns True if the strings are equal.  The comparison still exposes type
    and length, and `str` arguments must first be UTF-8 encoded.  The
    arguments can be `str` or `bytes`, but mixed types are not allowed.
    """
    if isinstance(a, bytes):
        if not isinstance(b, bytes):
            raise TypeError(
                'mixed string and bytes arguments are not allowed'
            )
        left = a
        right = b
    else:
        if not isinstance(b, str):
            raise TypeError(
                'mixed string and bytes arguments are not allowed'
            )
        left = a.encode('utf-8')
        right = b.encode('utf-8')
    result = 0 if len(left) == len(right) else 1
    for x, y in zip(left, right):
        result |= x ^ y
    return result == 0


def import_object(name: str) -> object:
    """Import and return the module or object named by `name`.

    If `name` has no dot, import and return that module.  If it is dotted,
    import the module prefix and return the final component as an attribute
    of that module, e.g. ``'quixote.publish.Publisher'``.  Used to resolve
    string references from configuration to the object itself.
    """
    i = name.rfind('.')
    if i != -1:
        module_name = name[:i]
        object_name = name[i + 1 :]
        __import__(module_name)
        return getattr(sys.modules[module_name], object_name)
    else:
        __import__(name)
        return sys.modules[name]


def xmlrpc(
    request: HTTPRequest,
    func: Callable[[str, tuple[object, ...]], object],
) -> str:
    """Dispatch an XML-RPC request body and return the XML-RPC response.

    Reads the POST body of `request`, decodes the method call, and invokes
    `func(method_name, params)`.  The return value (or a raised
    `xmlrpc.client.Fault`, or any other exception) is encoded as an XML-RPC
    response.  Rejects non-POST requests with a 405.
    """

    # Get contents of POST body
    if request.get_method() != 'POST':
        request.response.set_status(405, "Only the POST method is accepted")
        return "XML-RPC handlers only accept the POST method."

    length = int(request.environ['CONTENT_LENGTH'])
    stdin = request.stdin
    if stdin is None:
        raise RuntimeError('request has no input stream')
    data = stdin.read(length)

    # Parse arguments
    params, method = _xmlrpc.loads(data)
    method_name = cast(str, method)
    method_params = cast(tuple[object, ...], params)

    try:
        result = func(method_name, method_params)
    except _xmlrpc.Fault as exc:
        payload = _xmlrpc.dumps(exc)
    except BaseException:
        # report exception back to client
        payload = _xmlrpc.dumps(
            _xmlrpc.Fault(1, "%s:%s" % (sys.exc_info()[0], sys.exc_info()[1]))
        )
    else:
        payload = _xmlrpc.dumps(
            cast(Any, (result,)),
            methodresponse=True,
        )

    request.response.set_content_type('text/xml')
    return payload


class FileStream(Stream):
    """A response `Stream` that yields an open file in chunks.

    Return one from a controller (optionally wrapped by the response body
    machinery) to stream a download straight from a file object without
    reading it fully into memory.  Pass `size` when the length is known so a
    Content-Length header can be set.
    """

    CHUNK_SIZE = 20000

    fp: IO[bytes]
    length: int | None

    def __init__(self, fp: IO[bytes], size: int | None = None) -> None:
        """Wrap the open binary file `fp`, of `size` bytes if known."""
        self.fp = fp
        self.length = size

    def __iter__(self) -> FileStream:
        return self

    def __next__(self) -> bytes:
        chunk = self.fp.read(self.CHUNK_SIZE)
        if not chunk:
            raise StopIteration
        return chunk

    def close(self) -> None:
        """Close the underlying file object once the stream is exhausted."""
        if hasattr(self.fp, 'close'):
            self.fp.close()


class StaticFile:
    """Serve a single file from the filesystem as a Quixote resource.

    Assign an instance to an exported name in a `Directory` (or return one
    from `_q_lookup`); calling it serves the file, handling Content-Type,
    optional caching via an Expires header, and If-Modified-Since.
    """

    path: FilePath
    follow_symlinks: bool
    mime_type: str
    encoding: str | None
    cache_time: int | None

    def __init__(
        self,
        path: FilePath,
        follow_symlinks: bool = False,
        mime_type: str | None = None,
        encoding: str | None = None,
        cache_time: int | None = None,
    ) -> None:
        """Wrap the file at absolute `path`.

        `path` must be absolute (a relative path raises `ValueError`).  If
        `follow_symlinks` is true, a symlinked path is served rather than
        rejected.  `mime_type` and `encoding` override the values guessed
        from the filename; `encoding` is the HTTP Content-Encoding, not a
        response charset (the MIME type defaults to text/plain).
        `cache_time`, if given, is the number of seconds the response stays
        valid and sets the Expires header; None leaves Expires unset.
        """

        # Check that the supplied path is absolute and (if a symbolic
        # link) may be followed
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

    def get_data(self) -> bytes:
        """Read and return the file's raw bytes."""
        with open(self.path, 'rb') as fp:
            data = fp.read()
        return data

    def __call__(self) -> StaticResult:
        """Serve the file as the response body.

        Sets Content-Type and caching headers and returns a `FileStream` for
        the file, or an empty body with status 304 when the client's
        If-Modified-Since matches.  Raises `TraversalError` (404) if the path
        is missing, is not a regular file, or is a disallowed symlink.
        """
        if not self.follow_symlinks and os.path.islink(self.path):
            raise errors.TraversalError(
                private_msg="Path %r is a symlink" % self.path
            )
        if not os.path.isfile(self.path):
            raise errors.TraversalError(
                private_msg="Path %r is not a file" % self.path
            )
        request = quixote.current_request()
        response = quixote.current_response()

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

        # Set the Content-Type for the response and return the file's
        # contents.
        response.set_content_type(self.mime_type)
        if self.encoding:
            response.set_header("Content-Encoding", self.encoding)

        response.set_header('Last-Modified', last_modified)

        return FileStream(open(self.path, 'rb'), stat.st_size)


class StaticDirectory(Directory):
    """Serve a filesystem directory tree as a Quixote `Directory`.

    Each request component names a file (served via `file_class`, a
    `StaticFile` by default) or a subdirectory (served by another
    `StaticDirectory`).  Optionally lists directory contents, serves index
    files, follows symlinks, and caches wrapped files in memory.
    """

    _q_exports = ['']

    FILE_CLASS: type[StaticFile] = StaticFile

    path: FilePath
    use_cache: bool
    cache: dict[str, StaticItem]
    list_directory: bool
    follow_symlinks: bool
    cache_time: int | None
    file_class: type[StaticFile]
    index_filenames: Sequence[str] | None

    def __init__(
        self,
        path: FilePath,
        use_cache: bool = False,
        list_directory: bool = False,
        follow_symlinks: bool = False,
        cache_time: int | None = None,
        file_class: type[StaticFile] | None = None,
        index_filenames: Sequence[str] | None = None,
    ) -> None:
        """Serve the tree rooted at absolute `path`.

        `path` must be absolute (a relative path raises `ValueError`).  If
        `use_cache` is true, wrapped files are cached in memory.  If
        `list_directory` is true, a request for the directory returns an HTML
        listing.  If `follow_symlinks` is true, symlinks are followed.
        `cache_time` sets the Expires header on served files (see
        `StaticFile`).  `file_class` overrides the wrapper used for files.
        `index_filenames` names index files to serve for the directory
        itself, tried left to right.
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

    def _q_index(self) -> object:
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
                    return cast(Callable[[], object], obj)()
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
                marker = '/' if os.path.isdir(filepath) else ''
                r += template % (
                    urllib.parse.quote(filename),
                    filename,
                    marker,
                )
            r += htmltext('</pre>')
            body = cast(htmltext, r.getvalue())
        else:
            title = 'Directory listing denied'
            body = htmltext(
                '<p>This directory does not allow its contents '
                'to be listed.</p>'
            )
        return errors.format_page(title, body)

    def _q_lookup(self, name: str, /) -> StaticItem:
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
    """A static-like file that exists only in memory, not on disk.

    The data for the file is stored as a 'str' object.
    """

    data: str
    mime_type: str
    encoding: str
    cache_time: int | None

    def __init__(
        self,
        data: str,
        mime_type: str | None = None,
        encoding: str | None = None,
        cache_time: int | None = None,
    ) -> None:
        """Hold `data` as a file with the given MIME type and encoding.

        `mime_type` defaults to text/plain and `encoding` to the Quixote
        default charset.  A truthy `cache_time` sets the Expires header when
        the file is served.
        """
        self.data = data
        self.mime_type = mime_type or 'text/plain'
        self.encoding = encoding or quixote.DEFAULT_CHARSET
        self.cache_time = cache_time

    def get_data(self) -> bytes:
        """Return the file's content as UTF-8 encoded bytes."""
        return self.data.encode('utf-8')

    def __call__(self) -> str:
        """Serve the in-memory data as the response body."""
        response = quixote.current_response()
        response.set_content_type(self.mime_type, self.encoding)
        if self.cache_time:
            response.set_expires(seconds=self.cache_time)
        return self.data


@functools.cache
def _get_static_file_hash(
    static_file: StaticFile | MemoryFile,
) -> str:
    """Return hex-digest hash of the static file content."""
    return hashlib.sha1(static_file.get_data()).hexdigest()


class StaticBundle(Directory):
    """A virtual directory that holds static files.

    Can be used for Javascript, CSS files, and images.  It can optionally
    concatenate multiple text files into a single file (e.g. Javascript).  A
    token based on the content hash of the file is used as part of the URL and
    so a very long cache time can be specified.  Hashed URLs are served with
    `CACHE_TIME` seconds of cache lifetime.

    Additional notes:

    * All files stored under 'dirname' are potentially exposed, even if you
      don't explicitly link to them.  So don't put anything in that folder
      that shouldn't be public.

    * File content is cached in memory and does not expire.  So, if you are
      serving large files, this is probably not the way to do it.  It is
      intended for serving things like CSS and Javascript.

    * If the file content changes while Quixote is running, the content ID
      is not re-computed.  If you modify the file, you need to restart the
      Quixote application.
    """

    # Because we generate a path based on the file content hash it is safe to
    # use a very long cache time.
    CACHE_TIME = 3600 * 24 * 100

    basedir: FilePath
    basepath: str
    sep: str
    encoding: str
    files: dict[str, StaticFile | MemoryFile]
    paths: dict[str, str]

    def __init__(
        self,
        dirname: FilePath,
        basepath: str = '',
        sep: str = '\n',
        encoding: str | None = None,
    ) -> None:
        """Create a new StaticBundle.

        'dirname' is a file path to the files on disk.  'basepath' is the base
        web path for the files and is used by make_path() to generate an
        absolute path URL.  If files are to be concatenated, 'sep' is used
        as a separator between files. Using newline is the default since
        minimized Javascript and CSS sometimes are missing a final newline.
        """
        self.basedir = dirname
        self.basepath = basepath
        self.sep = sep
        self.encoding = encoding or quixote.DEFAULT_CHARSET
        self.files = {}
        self.paths = {}

    def _create_bundle(self, filenames: Sequence[str]) -> MemoryFile:
        """Generate concatenated data for 'filenames'.

        Return a MemoryFile object containing the data.
        """
        data = io.StringIO()
        mime_type: str | None = None
        for index, fn in enumerate(filenames):
            if fn == '..' or '/' in fn:
                # should not happen, check anyhow
                raise ValueError('invalid file name for static file')
            filename = os.path.join(self.basedir, fn)
            if not os.path.isfile(filename):
                raise errors.TraversalError('static file missing')
            with open(filename, 'r', encoding=self.encoding) as fp:
                data.write(fp.read())
            if index + 1 < len(filenames):
                data.write(self.sep)
            if mime_type is None:
                mime_type, _guess_enc = mimetypes.guess_type(
                    fn,
                    strict=False,
                )
        return MemoryFile(
            data.getvalue(),
            mime_type=mime_type,
            encoding=self.encoding,
        )

    def _get_static_file(
        self,
        filename: str,
        cache_time: int | None = None,
    ) -> StaticFile | MemoryFile:
        """Return static file object for 'filename'."""
        static_file = self.files.get(filename)
        if static_file is not None:
            return static_file
        if ',' in filename:
            # it is a virtual file created by concatenating text files
            static_file = self._create_bundle(filename.split(','))
        else:
            static_file = StaticFile(
                os.path.join(self.basedir, filename),
                encoding=self.encoding,
            )
        if cache_time:
            static_file.cache_time = cache_time
        self.files[filename] = static_file
        return static_file

    def _get_content_hash_token(self, filename: str) -> str:
        """Return a token based on the content of the file.

        If the content changes then this token is very likely to change as
        well.
        """
        # Previously we used the modification time here but a content hash is
        # more reliable and works with re-producible builds.
        static_file = self._get_static_file(filename)
        hash_value = _get_static_file_hash(static_file)
        return hash_value[:10]

    def make_path(self, *filenames: object) -> str:
        """Generate a path for a file or list of files.

        The returned path will include a path component based on the content.
        If multiple file names are provided, they must all have the same
        extension.
        """
        filename_parts = [str(fn) for fn in filenames]
        key = ','.join(filename_parts)
        path = self.paths.get(key)
        if path is not None:
            return path
        exts = {os.path.splitext(fn)[1] for fn in filename_parts}
        if len(exts) != 1:
            raise ValueError('different file extensions %s' % exts)
        for fn in filename_parts:
            fn = os.path.join(self.basedir, fn)
            if not os.path.exists(fn):
                raise ValueError('missing file %r' % fn)
        token = self._get_content_hash_token(key)
        path = '%s/%s/%s' % (self.basepath, token, key)
        self.paths[key] = path
        return path

    def _q_traverse(self, path: list[str], /) -> StaticResult:
        if len(path) == 1:
            # if hash token component missing, allow direct path, no caching
            filename = path[0]
            token = ''
            cache_time = None
        elif len(path) == 2:
            # path with a cache busting content hash token
            filename = path[1]
            if filename == '..':
                raise errors.TraversalError('invalid static file path')
            token = path[0]
            cache_time = self.CACHE_TIME
        else:
            raise errors.TraversalError()
        static_file = self._get_static_file(filename, cache_time)
        if token and token != self._get_content_hash_token(filename):
            raise errors.TraversalError(
                'file does not exist with that content'
            )
        return static_file()


class Redirector:
    """A callable object that redirects a request to a fixed URL.

    Return one from `_q_lookup` (or export it) to redirect a URL that ends at
    that traversal point to `location`.
    """

    _q_exports: list[str] = []

    location: str
    permanent: bool

    def __init__(self, location: str, permanent: bool = False) -> None:
        """Redirect to `location`; a permanent redirect uses HTTP 301."""
        self.location = location
        self.permanent = permanent

    def _q_lookup(self, component: str, /) -> Redirector:
        """Return self for custom traversal code that calls this lookup."""
        return self

    def __call__(self) -> object:
        """Issue the redirect to `location`."""
        return quixote.redirect(self.location, self.permanent)


def dump_request(request: HTTPRequest | None = None) -> htmltext:
    """Dump an HTTPRequest object as HTML."""
    if request is None:
        request = quixote.current_request()
    row_fmt = htmltext('<tr><th>%s</th><td>%s</td></tr>')
    r = TemplateIO(html=True)
    r += htmltext('<h3>form</h3><table>')
    for k, v in request.form.items():
        r += row_fmt % (k, v)
    r += htmltext('</table><h3>cookies</h3><table>')
    for k, v in request.cookies.items():
        r += row_fmt % (k, v)
    r += htmltext('</table><h3>environ</h3><table>')
    for k, v in request.environ.items():
        r += row_fmt % (k, v)
    r += htmltext('</table>')
    return cast(htmltext, r.getvalue())


def get_directory_path() -> list[object]:
    """Return the list of traversed instances."""
    path: list[object] = []
    frame = sys._getframe()
    while frame:
        if frame.f_code.co_name == '_q_traverse':
            self = frame.f_locals.get('self', None)
            if path[:1] != [self]:
                path.insert(0, self)
        frame = frame.f_back
    return path
