# Inherit activation sockets from systemd, see systemd man page for
# sd_listen_fds().
import os
import socket

SD_LISTEN_FDS_START = 3


def _set_close_on_exec(fds):
    try:
        import fcntl
    except ImportError:
        return
    if not hasattr(fcntl, 'FD_CLOEXEC'):
        return
    for fd in range(SD_LISTEN_FDS_START, SD_LISTEN_FDS_START + fds):
        fcntl.fcntl(fd, fcntl.F_SETFD, fcntl.FD_CLOEXEC)


def sd_listen_fds():
    """Return the number of inherited sockets.  Return zero if there are
    none.
    """
    try:
        pid = int(os.environ['LISTEN_PID'])
    except (ValueError, KeyError):
        return 0
    if os.getpid() != pid:
        return 0
    try:
        fds = int(os.environ['LISTEN_FDS'])
    except (ValueError, KeyError):
        raise OSError('invalid LISTEN_FDS value')
    _set_close_on_exec(fds)
    return fds


def _socket_from_fd(fd):
    # This is ugly; Python doesn't provide a nice way to use
    # getsockopt() and getsockname() to determine the type of
    # socket.  Using AF_UNIX is a kludge to avoid messing up the
    # getsockname() return value.
    s = socket.fromfd(fd, socket.AF_UNIX, socket.SOCK_STREAM)
    name = s.getsockname()
    s.close()  # fromfd() calls dup, close the new fd
    if isinstance(name, (str, bytes)):
        family = socket.AF_UNIX
    elif ':' in name[0]:
        family = socket.AF_INET6
    else:
        family = socket.AF_INET
    # we assume we are getting a SOCK_STREAM socket
    s = socket.fromfd(fd, family, socket.SOCK_STREAM)
    os.close(fd)  # fromfd() calls dup, close old fd
    return s


def get_systemd_socket():
    """Return the inherited socket, if there is one.  If not, return None."""
    num = sd_listen_fds()
    if not num:
        return None
    if num > 1:
        raise OSError('only one inherited socket supported')
    sock = _socket_from_fd(SD_LISTEN_FDS_START)
    return sock
