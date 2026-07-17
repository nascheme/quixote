import importlib
import types
from typing import Any


class _LazyModule(types.ModuleType):
    def __init__(self, fullname: str) -> None:
        self._lazy_module_name = fullname

    def __getattribute__(self, attr: str) -> Any:
        # Stop triggering this method.
        # pyrefly: ignore [bad-argument-type]
        self.__class__ = types.ModuleType
        # Import the real module
        mod = importlib.import_module(self._lazy_module_name)
        # Set dict contents from real module
        for k, v in mod.__dict__.items():
            if k not in self.__dict__:
                self.__dict__[k] = v
        return getattr(self, attr)

    def __delattr__(self, attr: str) -> None:
        # Trigger the load and then perform the deletion.
        self.__getattribute__(attr)
        delattr(self, attr)


def load(fullname: str) -> _LazyModule:
    """Return a lazily imported proxy for a module.

    We often see the following pattern::

      def myfunc():
          import scipy as sp
          sp.argmin(...)
          ....

    This is to prevent a module, in this case `scipy`, from being
    imported at function definition time, since that can be slow.

    This function provides a proxy module that, upon access, imports
    the actual module.  So the idiom equivalent to the above example is::

      sp = load("scipy")

      def myfunc():
          sp.argmin(...)
          ....

    The initial import time is fast because the actual import is delayed
    until the first attribute is requested. The overall import time may
    decrease as well for users that don't make use of large portions
    of the library.

    Parameters
    ----------
    fullname : str
        The full name of the module or submodule to import.  For example::

          sp = load('scipy')  # import scipy as sp
          spla = load('scipy.linalg')  # import scipy.linalg as spla

    Returns
    -------
    pm : _LazyModule
        Proxy module.  Can be used like any regularly imported module.
        Actual loading of the module occurs upon first attribute request.

    """
    return _LazyModule(fullname)
