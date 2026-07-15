"""quixote.sendmail

Tools for sending mail from Quixote applications.
"""

from __future__ import annotations

import datetime
import email.utils
from collections.abc import Sequence
from email.header import Header
from smtplib import SMTP
from typing import TYPE_CHECKING, cast, overload

if TYPE_CHECKING:
    from quixote.config import Config

try:
    import ssl
    from smtplib import SMTP_SSL
except ImportError:
    ssl = None

EMAIL_ENCODING = 'utf-8'

MailboxTuple = tuple[str] | tuple[str, str]


class RFC822Mailbox:
    """
    In RFC 822, a "mailbox" is either a bare e-mail address or a bare
    e-mail address coupled with a chunk of text, most often someone's
    name.  Eg. the following are all "mailboxes" in the RFC 822 grammar:
      luser@example.com
      Joe Luser <luser@example.com>
      Paddy O'Reilly <paddy@example.ie>
      "Smith, John" <smith@example.com>
      Dick & Jane <dickjane@example.net>
      "Tom, Dick, & Harry" <tdh@example.org>

    This class represents an (addr_spec, real_name) pair and takes care
    of quoting the real_name according to RFC 822's rules for you.
    Just use the format() method and it will spit out a properly-
    quoted RFC 822 "mailbox".
    """

    addr_spec: str
    real_name: str | None

    @overload
    def __init__(self, addr_spec: str, /) -> None: ...

    @overload
    def __init__(self, addr_spec: str, real_name: str | None, /) -> None: ...

    @overload
    def __init__(self, mailbox: MailboxTuple, /) -> None: ...

    def __init__(self, *args: object) -> None:
        """Create a mailbox from an address and optional real name.

        For convenience the address and name may be passed as two positional
        arguments, as a single ``(addr_spec, real_name)`` tuple, or as just an
        `addr_spec` (string or 1-tuple) with no name.  Raises `TypeError` for
        any other number of arguments.
        """
        if len(args) == 1 and type(args[0]) is tuple:
            args = args[0]

        if len(args) == 1:
            addr_spec = cast(str, args[0])
            real_name = None
        elif len(args) == 2:
            addr_spec = cast(str, args[0])
            real_name = cast(str | None, args[1])
        else:
            raise TypeError(
                "invalid number of arguments: "
                "expected 1 or 2 strings or "
                "a tuple of 1 or 2 strings"
            )

        self.addr_spec = addr_spec
        self.real_name = real_name

    def __str__(self) -> str:
        return self.addr_spec

    def __repr__(self) -> str:
        return "<%s at %x: %s>" % (self.__class__.__name__, id(self), self)

    def format(self) -> str:
        """Return the RFC 822 mailbox string, quoting the real name.

        With a real name this yields ``Real Name <addr@host>`` (the name
        quoted as the grammar requires); without one it yields the bare
        address.
        """
        if self.real_name:
            return email.utils.formataddr((self.real_name, self.addr_spec))
        else:
            return self.addr_spec


MailboxInput = str | MailboxTuple | RFC822Mailbox


@overload
def _ensure_mailbox(s: None) -> None: ...


@overload
def _ensure_mailbox(s: MailboxInput) -> RFC822Mailbox: ...


def _ensure_mailbox(s: MailboxInput | None) -> RFC822Mailbox | None:
    """_ensure_mailbox(s : string |
                          (string,) |
                          (string, string) |
                          RFC822Mailbox |
                          None)
       -> RFC822Mailbox | None

    If s is a string, or a tuple of 1 or 2 strings, returns an
    RFC822Mailbox encapsulating them as an addr_spec and real_name.  If
    s is already an RFC822Mailbox, returns s.  If s is None, returns
    None.
    """
    if s is None or isinstance(s, RFC822Mailbox):
        return s
    else:
        return RFC822Mailbox(s)


# Maximum number of recipients that will be explicitly listed in
# any single message header.  Eg. if MAX_HEADER_RECIPIENTS is 10,
# there could be up to 10 "To" recipients and 10 "CC" recipients
# explicitly listed in the message headers.
MAX_HEADER_RECIPIENTS = 10


def _add_recip_headers(
    headers: list[str], field_name: str, addrs: Sequence[RFC822Mailbox]
) -> None:
    if not addrs:
        return
    formatted_addrs = [addr.format() for addr in addrs]

    if len(formatted_addrs) == 1:
        headers.append("%s: %s" % (field_name, formatted_addrs[0]))
    elif len(formatted_addrs) <= MAX_HEADER_RECIPIENTS:
        headers.append("%s: %s," % (field_name, formatted_addrs[0]))
        for addr in formatted_addrs[1:-1]:
            headers.append("    %s," % addr)
        headers.append("    %s" % formatted_addrs[-1])
    else:
        headers.append(
            "%s: (long recipient list suppressed) : ;" % field_name
        )


def _encode_header(s: str) -> str:
    try:
        s.encode('ascii')
    except UnicodeEncodeError:
        return Header(s).encode(EMAIL_ENCODING)
    else:
        return s


def sendmail(
    subject: str,
    msg_body: str,
    to_addrs: list[MailboxInput],
    from_addr: MailboxInput | None = None,
    cc_addrs: list[MailboxInput] | None = None,
    extra_headers: Sequence[str] | None = None,
    smtp_sender: MailboxInput | None = None,
    smtp_recipients: list[MailboxInput] | None = None,
    mail_server: str | None = None,
    mail_debug_addr: str | None = None,
    username: str | None = None,
    password: str | None = None,
    mail_port: int | None = None,
    use_ssl: bool = False,
    use_tls: bool = False,
    config: Config | None = None,
) -> None:
    """
    Send an email message to a list of recipients via a local SMTP
    server.  In normal use, you supply a list of primary recipient
    e-mail addresses in 'to_addrs', an optional list of secondary
    recipient addresses in 'cc_addrs', and a sender address in
    'from_addr'.  sendmail() then constructs a message using those
    addresses, 'subject', and 'msg_body', and mails the message to every
    recipient address.  (Specifically, it connects to the mail server
    named in the MAIL_SERVER config variable -- default "localhost" --
    and instructs the server to send the message to every recipient
    address in 'to_addrs' and 'cc_addrs'.)

    'from_addr' is optional because web applications often have a common
    e-mail sender address, such as "webmaster@example.com".  Just set
    the Quixote config variable MAIL_FROM, and it will be used as the
    default sender (both header and envelope) for all e-mail sent by
    sendmail().

    E-mail addresses can be specified a number of ways.  The most
    efficient is to supply instances of RFC822Mailbox, which bundles a
    bare e-mail address (aka "addr_spec" from the RFC 822 grammar) and
    real name together in a readily-formattable object.  You can also
    supply an (addr_spec, real_name) tuple, or an addr_spec on its own.
    The latter two are converted into RFC822Mailbox objects for
    formatting, which is why it may be more efficient to construct
    RFC822Mailbox objects yourself.

    Thus, the following are all equivalent in terms of who gets the
    message:
      sendmail(to_addrs=["joe@example.com"], ...)
      sendmail(to_addrs=[("joe@example.com", "Joe User")], ...)
      sendmail(to_addrs=[RFC822Mailbox("joe@example.com", "Joe User")], ...)
    ...although the "To" header will be slightly different.  In the
    first case, it will be
      To: joe@example.com
    while in the other two, it will be:
      To: Joe User <joe@example.com>
    which is a little more user-friendly.

    In more advanced usage, you might wish to specify the SMTP sender
    and recipient addresses separately.  For example, if you want your
    application to send mail to users that looks like it comes from a
    real human being, but you don't want that human being to get the
    bounce messages from the mailing, you might do this:
      sendmail(to_addrs=user_list,
               ...,
               from_addr=("realuser@example.com", "A Real User"),
               smtp_sender="postmaster@example.com")

    End users will see mail from "A Real User <realuser@example.com>" in
    their inbox, but bounces will go to postmaster@example.com.

    One use of different header and envelope recipients is for
    testing/debugging.  If you want to test that your application is
    sending the right mail to bigboss@example.com without filling
    bigboss' inbox with dross, you might do this:
      sendmail(to_addrs=["bigboss@example.com"],
               ...,
               smtp_recipients=["developers@example.com"])

    This is so useful that it's a Quixote configuration option: just set
    MAIL_DEBUG_ADDR to (eg.) "developers@example.com", and every message
    that sendmail() would send out is diverted to the debug address.

    Generally raises an exception on any SMTP errors; see smtplib (in
    the standard library documentation) for details.
    """
    if config is None and not mail_server:
        from quixote import get_publisher

        publisher = get_publisher()
        if publisher is not None:
            config = publisher.config

    if not from_addr and config is not None:
        from_addr = config.mail_from
    if not mail_server and config is not None:
        mail_server = config.mail_server
    if config is not None:
        mail_debug_addr = mail_debug_addr or config.mail_debug_addr
        username = username or config.mail_username
        password = password or config.mail_password
        mail_port = mail_port or config.mail_port
        use_ssl = use_ssl or config.mail_use_ssl
        use_tls = use_tls or config.mail_use_tls

    if not isinstance(to_addrs, list):
        raise TypeError("'to_addrs' must be a list")
    if not (cc_addrs is None or isinstance(cc_addrs, list)):
        raise TypeError("'cc_addrs' must be a list or None")

    # Make sure we have a "From" address
    from_mailbox = _ensure_mailbox(from_addr)
    if from_mailbox is None:
        raise RuntimeError(
            "no from_addr supplied, and MAIL_FROM not set in config file"
        )
    if mail_server is None:
        raise RuntimeError(
            "no mail_server supplied, and MAIL_SERVER not set in config file"
        )

    # Ensure all of our addresses are really RFC822Mailbox objects.
    to_mailboxes = [_ensure_mailbox(addr) for addr in to_addrs]
    cc_mailboxes = (
        [_ensure_mailbox(addr) for addr in cc_addrs] if cc_addrs else None
    )

    # Start building the message headers.
    headers = [
        "From: %s" % from_mailbox.format(),
        "Subject: %s" % _encode_header(subject),
        "Date: %s" % email.utils.format_datetime(datetime.datetime.now()),
    ]
    _add_recip_headers(headers, "To", to_mailboxes)
    if cc_mailboxes:
        _add_recip_headers(headers, "Cc", cc_mailboxes)

    if extra_headers:
        headers.extend(extra_headers)

    # add a Content-Type header if there isn't already one
    for hdr in headers:
        name, _, value = hdr.partition(':')
        if name.lower() == 'content-type':
            break
    else:
        headers.append(
            'Content-Type: text/plain; charset=%s' % EMAIL_ENCODING
        )

    if mail_debug_addr:
        debug1 = (
            "[debug mode, message actually sent to %s]\n" % mail_debug_addr
        )
        if smtp_recipients:
            debug2 = "[original SMTP recipients: %s]\n" % ", ".join(
                _ensure_mailbox(recip).addr_spec for recip in smtp_recipients
            )
        else:
            debug2 = ""

        sep = ("-" * 72) + "\n"
        msg_body = debug1 + debug2 + sep + msg_body

        smtp_recipients = [mail_debug_addr]

    if smtp_sender is None:
        smtp_sender_addr = from_mailbox.addr_spec
    else:
        smtp_sender_addr = _ensure_mailbox(smtp_sender).addr_spec

    if smtp_recipients is None:
        smtp_recipient_addrs = [addr.addr_spec for addr in to_mailboxes]
        if cc_mailboxes:
            smtp_recipient_addrs.extend(
                [addr.addr_spec for addr in cc_mailboxes]
            )
    else:
        smtp_recipient_addrs = [
            _ensure_mailbox(recip).addr_spec for recip in smtp_recipients
        ]

    message = "\n".join(headers) + "\n\n" + msg_body
    # smtplib requires bytes
    message = message.encode(EMAIL_ENCODING)

    if not mail_port:
        if use_ssl:
            mail_port = 465
        elif use_tls:
            mail_port = 587
        else:
            mail_port = 25

    if ssl and (use_ssl or use_tls):
        context = ssl.create_default_context(ssl.Purpose.SERVER_AUTH)
        if config and config.mail_allow_sslv3:
            # need to allow SSLv3 for old servers, even though it is broken
            context.options &= ~ssl.OP_NO_SSLv3
    else:
        context = None

    if use_ssl:
        smtp = SMTP_SSL(mail_server, port=mail_port, context=context)
    else:
        smtp = SMTP(mail_server, port=mail_port)
    smtp.ehlo()
    if use_tls:
        smtp.starttls(context=context)
        smtp.ehlo()
    if username:
        smtp.login(username, cast(str, password))
    smtp.sendmail(smtp_sender_addr, smtp_recipient_addrs, message)
    smtp.quit()
