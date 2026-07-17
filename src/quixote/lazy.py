# This is a simple implementation of lazily imported modules for
# Python.  The globals in this module, like "publish", are instances of
# _LazyModule.  The real module will be imported when an attribute of
# the _LazyModule object is accessed.

from __future__ import annotations

from typing import TYPE_CHECKING

from quixote.lazy_import import load

if TYPE_CHECKING:
    # If type checking, do actual (eager) import of the module.  That
    # allows the type checker to find the type signatures.  The lazy
    # module is opaque to the checker.
    import quixote.form1 as form1
    import quixote.logger as logger
    import quixote.publish as publish
    import quixote.session as session
else:
    form1 = load('quixote.form1')
    logger = load('quixote.logger')
    publish = load('quixote.publish')
    session = load('quixote.session')
