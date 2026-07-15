'''
PTL: Python Template Language

PTL is the templating language used by Quixote. See doc/PTL.html for
documentation.
'''

from collections.abc import Callable
from typing import TypeVar

from quixote.ptl.ptl_compile import compile_package  # noqa: F401

F = TypeVar('F', bound=Callable[..., object])


def _check_template(func: Callable[..., object]) -> None:
    # If this function was actually compiled as PTL, should have this symbol
    # in names.
    if '_q_TemplateIO' in func.__code__.co_names:
        raise SyntaxError('PTL is not compiled (missing .ptl extension?)')


def ptl_html(func: F) -> F:
    """Decorator for HTML template function."""
    # _check_template(func)
    return func


def ptl_plain(func: F) -> F:
    """Decorator for plain-text template function."""
    # _check_template(func)
    return func
