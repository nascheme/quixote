'''A Form subclass that provides close to the same API as the old form
class (useful for transitioning existing forms).
'''

from quixote import get_request, get_path, redirect
from quixote.form import Form as _Form, Widget, StringWidget, FileWidget, \
    PasswordWidget, TextWidget, CheckboxWidget, RadiobuttonsWidget, \
    SingleSelectWidget, SelectWidget, OptionSelectWidget, \
    MultipleSelectWidget, SubmitWidget, HiddenWidget, \
    FloatWidget, IntWidget
from quixote.html import url_quote

_widget_names = {
    "string" : StringWidget,
    "file" : FileWidget,
    "password" : PasswordWidget,
    "text" : TextWidget,
    "checkbox" : CheckboxWidget,
    "single_select" : SingleSelectWidget,
    "radiobuttons" : RadiobuttonsWidget,
    "multiple_select" : MultipleSelectWidget,
    "submit_button" : SubmitWidget,
    "hidden" : HiddenWidget,
    "float" : FloatWidget,
    "int" : IntWidget,
    "option_select" : OptionSelectWidget,
}


class Form(_Form):
    def __init__(self, action_url=None, *args, **kwargs):
        _Form.__init__(self, action=action_url, *args, **kwargs)
        self.cancel_url = None
        self.action_url = self.action

    def add_widget(self, widget_class, name, value=None,
                   title=None, hint=None, required=False, **kwargs):
        try:
            widget_class = _widget_names[widget_class]
        except KeyError:
            pass
        self.add(widget_class, name, value=value, title=title, hint=hint,
                 required=required, **kwargs)

    def add_submit_button(self, name, value):
        self.add_submit(name, value)

    def add_cancel_button(self, caption, url):
        self.add_submit("cancel", caption)
        self.cancel_url = url

    def get_action_url(self):
        action_url = url_quote(get_path())
        query = get_request().get_query()
        if query:
            action_url += "?" + query
        return action_url

    def render(self, action_url=None):
        if action_url:
            self.action_url = action_url
        return _Form.render(self)

    def process(self):
        values = {}
        request = get_request()
        for name, widget in self._names.items():
            values[name] = widget.parse()
        return values

    def action(self, submit, values):
        raise NotImplementedError("sub-classes must implement 'action()'")

    def handle(self):
        """handle() -> string

        Master method for handling forms.  It should be called after
        initializing a form.  Controls form action based on a request.  You
        probably should override 'process' and 'action' instead of
        overriding this method.
        """
        request = get_request()
        if not self.is_submitted():
            return self.render(self.action_url)
        submit = self.get_submit()
        if submit == "cancel":
            return redirect(self.cancel_url)
        values = self.process()
        if submit == True:
            # The form was submitted by an unregistered submit button, assume
            # that the submission was required to update the layout of the form.
            self.clear_errors()
            return self.render(self.action_url)

        if self.has_errors():
            return self.render(self.action_url)
        else:
            return self.action(submit, values)
