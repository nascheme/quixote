"""The web interface framework, consisting of Form and Widget base classes
(and a bunch of standard widget classes recognized by Form).
Application developers will typically create a Form instance each
form in their application; each form object will contain a number
of widget objects.  Custom widgets can be created by inheriting
and/or composing the standard widget classes.
"""

from quixote.form.form import Form, FormTokenWidget  # noqa: F401
from quixote.form.widget import (  # noqa: F401
    CheckboxWidget,
    CompositeWidget,
    FileWidget,
    FloatWidget,
    HiddenWidget,
    IntWidget,
    MultipleSelectWidget,
    OptionSelectWidget,
    PasswordWidget,
    RadiobuttonsWidget,
    SelectWidget,
    SingleSelectWidget,
    StringWidget,
    SubmitWidget,
    TextWidget,
    Widget,
    WidgetDict,
    WidgetList,
    WidgetValueError,
    subname,
)
