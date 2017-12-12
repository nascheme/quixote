"""Provides the Form class and related classes.  Forms are a convenient
way of building HTML forms that are composed of Widget objects.
"""

from quixote import get_request, get_session, get_publisher
from quixote.html import htmltag, htmltext, TemplateIO
from quixote.form.widget import HiddenWidget, StringWidget, TextWidget, \
    CheckboxWidget, SingleSelectWidget, RadiobuttonsWidget, \
    MultipleSelectWidget, ResetWidget, SubmitWidget, FloatWidget, \
    IntWidget, PasswordWidget


class FormTokenWidget(HiddenWidget):

    def _parse(self, request):
        token = request.form.get(self.name)
        session = get_session()
        if not session.has_form_token(token):
            self.error = 'invalid' # this error does not get displayed
        else:
            session.remove_form_token(token)

    def render_error(self, error):
        return ''

    def render(self):
        self.value = get_session().create_form_token()
        return HiddenWidget.render(self)


class Form(object):
    """
    Provides a high-level mechanism for collecting and processing user
    input that is based on HTML forms.

    Instance attributes:
      widgets : [Widget]
        widgets that are not subclasses of SubmitWidget or HiddenWidget
      submit_widgets : [SubmitWidget]
        subclasses of SubmitWidget, normally rendered at the end of the
        form
      hidden_widgets : [HiddenWidget]
        subclasses of HiddenWidget, normally rendered at the beginning
        of the form
      _names : { name:string : Widget }
        names used in the form and the widgets associated with them
    """

    TOKEN_NAME = "_form_id" # name of hidden token widget

    JAVASCRIPT_MARKUP = htmltext('<script type="text/javascript">\n'
                                 '<!--\n'
                                 '%s\n'
                                 '// -->\n'
                                 '</script>\n')

    TOKEN_NOTICE = htmltext('<div class="errornotice">'
                            'The form you have submitted is invalid.  Most '
                            'likely it has been successfully submitted once '
                            'already.  Please review the the form data '
                            'and submit the form again.'
                            '</div>')

    ERROR_NOTICE = htmltext('<div class="errornotice">'
                            'There were errors processing your form.  '
                            'See below for details.'
                            '</div>')

    def __init__(self,
                 method="post",
                 action=None,
                 enctype=None,
                 use_tokens=True,
                 **attrs):

        if method not in ("post", "get"):
            raise ValueError("Form method must be 'post' or 'get', "
                             "not %r" % method)
        self.method = method
        self.action = action or self._get_default_action()
        if 'class' not in attrs:
            attrs['class'] = 'quixote'
        self.attrs = attrs
        self.widgets = []
        self.submit_widgets = []
        self.hidden_widgets = []
        self._names = {}

        if enctype is not None and enctype not in (
            "application/x-www-form-urlencoded", "multipart/form-data"):
            raise ValueError("Form enctype must be "
                               "'application/x-www-form-urlencoded' or "
                               "'multipart/form-data', not %r" % enctype)
        self.enctype = enctype

        if use_tokens and self.method == "post":
            config = get_publisher().config
            if config.form_tokens:
                # unique token for each form, this prevents many cross-site
                # attacks and prevents a form from being submitted twice
                self.add(FormTokenWidget, self.TOKEN_NAME, value=None)

    def _get_default_action(self):
        query = get_request().get_query()
        if query:
            return "?" + query
        else:
            return ""

    # -- Form data access methods --------------------------------------

    def __getitem__(self, name):
        """(name:string) -> any
        Return a widget's value.  Raises KeyError if widget named 'name'
        does not exist.
        """
        try:
            return self._names[name].parse()
        except KeyError:
            raise KeyError('no widget named %r' % name)

    def __contains__(self, name):
        """Return true if the widget named 'name' is in the form."""
        return name in self._names

    def get(self, name, default=None):
        """(name:string, default=None) -> any
        Return a widget's value.  Returns 'default' if widget named 'name'
        does not exist.
        """
        widget = self._names.get(name)
        if widget is not None:
            return widget.parse()
        else:
            return default

    def get_widget(self, name):
        """(name:string) -> Widget | None
        Return the widget named 'name'.  Returns None if the widget does
        not exist.
        """
        return self._names.get(name)

    def get_submit_widgets(self):
        """() -> [SubmitWidget]
        """
        return self.submit_widgets

    def get_all_widgets(self):
        """() -> [Widget]
        Return all the widgets that have been added to the form.  Note that
        this while this list includes submit widgets and hidden widgets, it
        does not include sub-widgets (e.g. widgets that are part of
        CompositeWidgets)
        """
        return list(self._names.values())

    # -- Form processing and error checking ----------------------------

    def is_submitted(self):
        """() -> bool

        Return true if a form was submitted.  If the form method is 'POST'
        and the page was not requested using 'POST', then the form is not
        considered to be submitted.  If the form method is 'GET' then the
        form is considered submitted if there is any form data in the
        request.
        """
        request = get_request()
        if self.method == 'post':
            if request.get_method() == 'POST':
                return True
            else:
                return False
        else:
            return bool(request.form)

    def has_errors(self):
        """() -> bool

        Ensure that all components of the form have parsed themselves. Return
        true if any of them have errors.
        """
        request = get_request()
        has_errors = False
        if self.is_submitted():
            for widget in self.get_all_widgets():
                if widget.has_error(request=request):
                    has_errors =  True
        return has_errors

    def clear_errors(self):
        """Ensure that all components of the form have parsed themselves.
        Clear any errors that might have occured during parsing.
        """
        request = get_request()
        for widget in self.get_all_widgets():
            widget.clear_error(request)

    def force_value(self, name, value):
        """Force the value of a widget to be 'value', even if the form
        has been submitted and a different value is in the request form data.
        """
        widget = self.get_widget(name)
        if widget is None:
            raise ValueError('unknown widget %r' % name)
        widget.clear_error() # calls parse internally
        widget.set_value(value)

    def get_submit(self):
        """() -> string | bool

        Get the name of the submit button that was used to submit the
        current form.  If the form is submitted but not by any known
        SubmitWidget then return True.  Otherwise, return False.
        """
        request = get_request()
        for button in self.submit_widgets:
            if button.parse(request):
                return button.name
        else:
            if self.is_submitted():
                return True
            else:
                return False

    def set_error(self, name, error):
        """(name : string, error : string)
        Set the error attribute of the widget named 'name'.
        """
        widget = self._names.get(name)
        if not widget:
            raise KeyError("unknown name %r" % name)
        widget.set_error(error)

    # -- Form population methods ---------------------------------------

    def add(self, widget_class, name, *args, **kwargs):
        if name in self._names:
            raise ValueError("form already has '%s' widget" % name)
        # add 'id' attribute if not already present
        if 'id' not in kwargs:
            kwargs['id'] = name
        kwargs['form'] = self
        widget = widget_class(name, *args, **kwargs)
        self._names[name] = widget
        if isinstance(widget, SubmitWidget):
            self.submit_widgets.append(widget) # will be rendered at end
        elif isinstance(widget, HiddenWidget):
            self.hidden_widgets.append(widget) # will be render at beginning
        else:
            self.widgets.append(widget)

    # convenience methods

    def add_submit(self, name, value=None, **kwargs):
        self.add(SubmitWidget, name, value, **kwargs)

    def add_reset(self, name, value=None, **kwargs):
        self.add(ResetWidget, name, value, **kwargs)

    def add_hidden(self, name, value=None, **kwargs):
        self.add(HiddenWidget, name, value, **kwargs)

    def add_string(self, name, value=None, **kwargs):
        self.add(StringWidget, name, value, **kwargs)

    def add_text(self, name, value=None, **kwargs):
        self.add(TextWidget, name, value, **kwargs)

    def add_password(self, name, value=None, **kwargs):
        self.add(PasswordWidget, name, value, **kwargs)

    def add_checkbox(self, name, value=None, **kwargs):
        self.add(CheckboxWidget, name, value, **kwargs)

    def add_single_select(self, name, value=None, **kwargs):
        self.add(SingleSelectWidget, name, value, **kwargs)

    def add_multiple_select(self, name, value=None, **kwargs):
        self.add(MultipleSelectWidget, name, value, **kwargs)

    def add_radiobuttons(self, name, value=None, **kwargs):
        self.add(RadiobuttonsWidget, name, value, **kwargs)

    def add_float(self, name, value=None, **kwargs):
        self.add(FloatWidget, name, value, **kwargs)

    def add_int(self, name, value=None, **kwargs):
        self.add(IntWidget, name, value, **kwargs)


    # -- Layout (rendering) methods ------------------------------------

    def render(self):
        """() -> HTML text
        Render a form as HTML.
        """
        r = TemplateIO(html=True)
        r += self._render_start()
        r += self._render_body()
        r += self._render_finish()
        return r.getvalue()

    def _render_start(self):
        r = TemplateIO(html=True)
        r += htmltag('form', method=self.method,
                     enctype=self.enctype, action=self.action,
                     **self.attrs)
        r += self._render_hidden_widgets()
        return r.getvalue()

    def _render_finish(self):
        r = TemplateIO(html=True)
        r += htmltext('</form><br class="quixoteform" />')
        code = get_request().response.javascript_code
        if code:
            r += self._render_javascript(code)
        return r.getvalue()

    def _render_widgets(self):
        r = TemplateIO(html=True)
        for widget in self.widgets:
            r += widget.render()
        return r.getvalue()

    def _render_hidden_widgets(self):
        r = TemplateIO(html=True)
        for widget in self.hidden_widgets:
            r += widget.render()
        return r.getvalue()

    def _render_submit_widgets(self):
        r = TemplateIO(html=True)
        if self.submit_widgets:
            r += htmltext('<div class="submit">')
            for widget in self.submit_widgets:
                r += widget.render()
            r += htmltext('</div><br class="submit" />')
        return r.getvalue()

    def _render_error_notice(self):
        token_widget = self.get_widget(self.TOKEN_NAME)
        if token_widget is not None and token_widget.has_error():
            # form tokens are enabled but the token data in the request
            # does not match anything in the session.  It could be an
            # a cross-site attack but most likely the back button has
            # be used
            return self.TOKEN_NOTICE
        else:
            return self.ERROR_NOTICE

    def _render_javascript(self, javascript_code):
        """Render javacript code for the form.  Insert code lexically
        sorted by code_id.
        """
        form_code = []
        code_ids = sorted(javascript_code.keys())
        for code_id in code_ids:
            code = javascript_code[code_id]
            if code:
                form_code.append(code)
                javascript_code[code_id] = ''
        if form_code:
            return self.JAVASCRIPT_MARKUP % htmltext(''.join(form_code))
        else:
            return ''

    def _render_body(self):
        r = TemplateIO(html=True)
        if self.has_errors():
            r += self._render_error_notice()
        r += self._render_widgets()
        r += self._render_submit_widgets()
        return r.getvalue()
