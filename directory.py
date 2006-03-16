"""$HeadURL: svn+ssh://svn.mems-exchange.org/repos/trunk/quixote/directory.py $
$Id: directory.py 26606 2005-04-18 21:55:37Z rmasse $

Logic for traversing directory objects and generating output.
"""
import quixote
from quixote.errors import TraversalError

class Directory(object):
    """
    Instance attributes: none
    """

    # A list containing strings or 2-tuples of strings that map external
    # names to internal names.  Note that the empty string will be
    # implicitly mapped to '_q_index'.
    _q_exports = []

    def _q_translate(self, component):
        """(component : string) -> string | None

        Translate a path component into a Python identifier.  Returning
        None signifies that the component does not exist.
        """
        if component in self._q_exports:
            if component == '':
                return '_q_index' # implicit mapping
            else:
                return component
        else:
            # check for an explicit external to internal mapping
            for value in self._q_exports:
                if isinstance(value, tuple):
                    if value[0] == component:
                        return value[1]
            else:
                return None

    def _q_lookup(self, component):
        """(component : string) -> object

        Lookup a path component and return the corresponding object (usually
        a Directory, a method or a string).  Returning None signals that the
        component does not exist.
        """
        return None

    def _q_traverse(self, path):
        """(path: [string]) -> object

        Traverse a path and return the result.
        """
        assert len(path) > 0
        component = path[0]
        path = path[1:]
        name = self._q_translate(component)
        if name is not None:
            obj = getattr(self, name)
        else:
            obj = self._q_lookup(component)
        if obj is None:
            raise TraversalError(private_msg=('directory %r has no component '
                                              '%r' % (self, component)))
        if path:
            if hasattr(obj, '_q_traverse'):
                return obj._q_traverse(path)
            else:
                raise TraversalError
        elif callable(obj):
            return obj()
        else:
            return obj

    def __call__(self):
        if "" in self._q_exports and not quixote.get_request().form:
            # Fix missing trailing slash.
            path = quixote.get_path()
            print "Adding slash to: %r " % path
            return quixote.redirect(path + "/", permanent=True)
        else:
            raise TraversalError(private_msg=('directory %r is not '
                                              'callable' % self))

class AccessControlled(object):
    """
    A mix-in class that calls the _q_access() method before traversing
    into the directory.
    """
    def _q_access(self):
        pass

    def _q_traverse(self, path):
        self._q_access()
        return super(AccessControlled, self)._q_traverse(path)


class Resolving(object):
    """
    A mix-in class that provides the _q_resolve() method.  _q_resolve()
    is called if a component name appears in the _q_exports list but is
    not an instance attribute.  _q_resolve is expected to return the
    component object.
    """
    def _q_resolve(self, name):
        return None

    def _q_translate(self, component):
        name = super(Resolving, self)._q_translate(component)
        if name is not None and not hasattr(self, name):
            obj = self._q_resolve(name)
            setattr(self, name, obj)
        return name
