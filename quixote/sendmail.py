"""quixote.sendmail

Tools for sending mail from Quixote applications.
"""
import email.utils
from email.header import Header
from smtplib import SMTP
try:
    from smtplib import SMTP_SSL
    import ssl
except ImportError:
    ssl = None
import quixote

EMAIL_ENCODING = 'utf-8'

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

    def __init__(self, *args):
        """RFC822Mailbox(addr_spec : string, name : string)
           RFC822Mailbox(addr_spec : string)
           RFC822Mailbox((addr_spec : string, name : string))
           RFC822Mailbox((addr_spec : string))

        Create a new RFC822Mailbox instance.  The variety of call
        signatures is purely for your convenience.
        """
        if (len(args) == 1 and type(args[0]) is tuple):
            args = args[0]

        if len(args) == 1:
            addr_spec = args[0]
            real_name = None
        elif len(args) == 2:
            (addr_spec, real_name) = args
        else:
            raise TypeError(
                "invalid number of arguments: "
                "expected 1 or 2 strings or "
                "a tuple of 1 or 2 strings")

        self.addr_spec = addr_spec
        self.real_name = real_name

    def __str__(self):
        return self.addr_spec

    def __repr__(self):
        return "<%s at %x: %s>" % (self.__class__.__name__, id(self), self)

    def format(self):
        if self.real_name:
            return email.utils.formataddr((self.real_name, self.addr_spec))
        else:
            return self.addr_spec


def _ensure_mailbox(s):
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

def _add_recip_headers(headers, field_name, addrs):
    if not addrs:
        return
    addrs = [addr.format() for addr in addrs]

    if len(addrs) == 1:
        headers.append("%s: %s" % (field_name, addrs[0]))
    elif len(addrs) <= MAX_HEADER_RECIPIENTS:
        headers.append("%s: %s," % (field_name, addrs[0]))
        for addr in addrs[1:-1]:
            headers.append("    %s," % addr)
        headers.append("    %s" % addrs[-1])
    else:
        headers.append("%s: (long recipient list suppressed) : ;" % field_name)


def _encode_header(s):
    try:
        s.encode('ascii')
    except UnicodeEncodeError:
        return Header(s).encode(EMAIL_ENCODING)
    else:
        return s


def sendmail(subject, msg_body, to_addrs,
             from_addr=None, cc_addrs=None,
             extra_headers=None,
             smtp_sender=None, smtp_recipients=None,
             mail_server=None, mail_debug_addr=None,
             username=None, password=None, mail_port=None,
             use_ssl=False, use_tls=False, config=None):
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
    if not mail_server and config is None:
        from quixote import get_publisher
        config = get_publisher().config

    from_addr = from_addr or config.mail_from
    mail_server = mail_server or config.mail_server
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
    if from_addr is None:
        raise RuntimeError(
            "no from_addr supplied, and MAIL_FROM not set in config file")

    # Ensure all of our addresses are really RFC822Mailbox objects.
    from_addr = _ensure_mailbox(from_addr)
    to_addrs = list(map(_ensure_mailbox, to_addrs))
    if cc_addrs:
        cc_addrs = list(map(_ensure_mailbox, cc_addrs))

    # Start building the message headers.
    headers = ["From: %s" % from_addr.format(),
               "Subject: %s" % _encode_header(subject)]
    _add_recip_headers(headers, "To", to_addrs)
    if cc_addrs:
        _add_recip_headers(headers, "Cc", cc_addrs)

    if extra_headers:
        headers.extend(extra_headers)

    # add a Content-Type header if there isn't already one
    for hdr in headers:
        name, _, value = hdr.partition(':')
        if name.lower() == 'content-type':
            break
    else:
        headers.append('Content-Type: text/plain; charset=%s' % EMAIL_ENCODING)

    if mail_debug_addr:
        debug1 = ("[debug mode, message actually sent to %s]\n"
                  % mail_debug_addr)
        if smtp_recipients:
            debug2 = ("[original SMTP recipients: %s]\n"
                      % ", ".join(smtp_recipients))
        else:
            debug2 = ""

        sep = ("-"*72) + "\n"
        msg_body = debug1 + debug2 + sep + msg_body

        smtp_recipients = [mail_debug_addr]

    if smtp_sender is None:
        smtp_sender = from_addr.addr_spec
    else:
        smtp_sender = _ensure_mailbox(smtp_sender).addr_spec

    if smtp_recipients is None:
        smtp_recipients = [addr.addr_spec for addr in to_addrs]
        if cc_addrs:
            smtp_recipients.extend([addr.addr_spec for addr in cc_addrs])
    else:
        smtp_recipients = [_ensure_mailbox(recip).addr_spec
                           for recip in smtp_recipients]

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
        smtp.login(username, password)
    smtp.sendmail(smtp_sender, smtp_recipients, message)
    smtp.quit()
