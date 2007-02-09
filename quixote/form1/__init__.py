"""The web interface framework, consisting of Form and Widget base classes
(and a bunch of standard widget classes recognized by Form).
Application developers will typically create a Form subclass for each
form in their application; each form object will contain a number
of widget objects.  Custom widgets can be created by inheriting
and/or composing the standard widget classes.
"""

from quixote.form1.form import Form, register_widget_class, FormTokenWidget
from quixote.form1.widget import Widget, StringWidget, FileWidget, \
     PasswordWidget, TextWidget, CheckboxWidget, RadiobuttonsWidget, \
     SingleSelectWidget, SelectWidget, OptionSelectWidget, \
     MultipleSelectWidget, ListWidget, SubmitButtonWidget, HiddenWidget, \
     FloatWidget, IntWidget, CollapsibleListWidget, FormValueError

# Register the standard widget classes
register_widget_class(StringWidget)
register_widget_class(FileWidget)
register_widget_class(PasswordWidget)
register_widget_class(TextWidget)
register_widget_class(CheckboxWidget)
register_widget_class(RadiobuttonsWidget)
register_widget_class(SingleSelectWidget)
register_widget_class(OptionSelectWidget)
register_widget_class(MultipleSelectWidget)
register_widget_class(ListWidget)
register_widget_class(SubmitButtonWidget)
register_widget_class(HiddenWidget)
register_widget_class(FloatWidget)
register_widget_class(IntWidget)
register_widget_class(CollapsibleListWidget)
