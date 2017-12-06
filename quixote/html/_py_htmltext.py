"""Python implementation of the htmltext type, the htmlescape function and
TemplateIO.
"""

def _escape_string(s):
    if isinstance(s, bytes):
        raise TypeError('escape_string no longer accepts bytes')
    if not isinstance(s, str):
        raise TypeError('string object required')
    s = s.replace("&", "&amp;")
    s = s.replace("<", "&lt;")
    s = s.replace(">", "&gt;")
    s = s.replace('"', "&quot;")
    return s

# backwards comptibility, unneeded in Python 3
stringify = str

class htmltext(object):
    """The htmltext string-like type.  This type serves as a tag
    signifying that HTML special characters do not need to be escaped
    using entities.
    """

    __slots__ = ['s']

    def __init__(self, s):
        self.s = str(s)

    # XXX make read-only
    #def __setattr__(self, name, value):
    #    raise AttributeError, 'immutable object'

    def __getstate__(self):
        raise ValueError('htmltext objects should not be pickled')

    def __repr__(self):
        return '<htmltext %r>' % self.s

    def __str__(self):
        return self.s

    def __len__(self):
        return len(self.s)

    def __eq__(self, other):
        if isinstance(other, htmltext):
            return (self.s == other.s)
        return (self.s == other)

    def __lt__(self, other):
        if isinstance(other, htmltext):
            return (self.s < other.s)
        return (self.s < other)

    def __hash__(self):
        return hash(self.s)

    def __mod__(self, args):
        if isinstance(args, tuple):
            return htmltext(self.s % tuple(map(_wraparg, args)))
        else:
            return htmltext(self.s % _wraparg(args))

    def format(self, *args, **kwargs):
        args = list(map(_wraparg, args))
        newkw = {}
        for k, v in kwargs.items():
            newkw[k] = _wraparg(v)
        return htmltext(self.s.format(*args, **newkw))

    def __add__(self, other):
        if isinstance(other, str):
            return htmltext(self.s + _escape_string(other))
        elif isinstance(other, htmltext):
            return htmltext(self.s + other.s)
        else:
            return NotImplemented

    def __radd__(self, other):
        if isinstance(other, str):
            return htmltext(_escape_string(other) + self.s)
        else:
            return NotImplemented

    def __mul__(self, n):
        return htmltext(self.s * n)

    def join(self, items):
        quoted_items = []
        for item in items:
            if isinstance(item, htmltext):
                quoted_items.append(str(item))
            elif isinstance(item, str):
                quoted_items.append(_escape_string(item))
            else:
                raise TypeError('join() requires string arguments (got %r)' % item)
        return htmltext(self.s.join(quoted_items))

    def startswith(self, s):
        if isinstance(s, htmltext):
            s = s.s
        else:
            s = _escape_string(s)
        return self.s.startswith(s)

    def endswith(self, s):
        if isinstance(s, htmltext):
            s = s.s
        else:
            s = _escape_string(s)
        return self.s.endswith(s)

    def replace(self, old, new, count=-1):
        if isinstance(old, htmltext):
            old = old.s
        else:
            old = _escape_string(old)
        if isinstance(new, htmltext):
            new = new.s
        else:
            new = _escape_string(new)
        return htmltext(self.s.replace(old, new, count))

    def lower(self):
        return htmltext(self.s.lower())

    def upper(self):
        return htmltext(self.s.upper())

    def capitalize(self):
        return htmltext(self.s.capitalize())

class _QuoteWrapper(object):
    # helper for htmltext class __mod__

    __slots__ = ['value']

    def __init__(self, value):
        self.value = value

    def __str__(self):
        return _escape_string(str(self.value))

    def __repr__(self):
        return _escape_string(repr(self.value))

    def __getitem__(self, key):
        return _wraparg(self.value[key])



def _wraparg(arg):
    if isinstance(arg, htmltext):
        return str(arg)
    elif isinstance(arg, str):
        return _escape_string(arg)
    elif (isinstance(arg, int) or
          isinstance(arg, float)):
        # ints, floats are okay
        return arg
    else:
        # everything is gets wrapped
        return _QuoteWrapper(arg)

def htmlescape(s):
    """htmlescape(s) -> htmltext

    Return an 'htmltext' object using the argument.  If the argument is not
    already a 'htmltext' object then the HTML markup characters \", <, >,
    and & are first escaped.
    """
    if isinstance(s, htmltext):
        return s
    else:
        s = str(s)
    # inline _escape_string for speed
    s = s.replace("&", "&amp;") # must be done first
    s = s.replace("<", "&lt;")
    s = s.replace(">", "&gt;")
    s = s.replace('"', "&quot;")
    return htmltext(s)


class TemplateIO(object):
    """Collect output for PTL scripts.
    """

    __slots__ = ['html', 'data']

    def __init__(self, html=False):
        self.html = html
        self.data = []

    def __call__(self, s):
        if s is not None:
            self.data.append(s)

    def __iadd__(self, other):
        if other is not None:
            self.data.append(other)
        return self

    def __repr__(self):
        return ("<%s at %x: %d chunks>" %
                (self.__class__.__name__, id(self), len(self.data)))

    def __str__(self):
        return str(self.getvalue())

    def getvalue(self):
        if self.html:
            return htmltext('').join(map(htmlescape, self.data))
        else:
            return ''.join(map(str, self.data))
