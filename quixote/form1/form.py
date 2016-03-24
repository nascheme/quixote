"""Provides the Form class and bureaucracy for registering widget classes.
(The standard widget classes are registered automatically.)
"""

from types import StringType
from quixote import get_session, get_publisher, redirect
from quixote.html import url_quote, htmltag, htmltext, nl2br, TemplateIO
from quixote.form1.widget import FormValueError, HiddenWidget


class FormTokenWidget (HiddenWidget):
    def render(self, request):
        self.value = get_session().create_form_token()
        return HiddenWidget.render(self, request)


JAVASCRIPT_MARKUP = htmltext('''\
<script type="text/javascript">
<!--
%s
// -->
</script>
''')

class Form:
    """
    A form is the major element of an interactive web page.  A form
    consists of the following:
      * widgets (input/interaction elements)
      * text
      * layout
      * code to process the form

    All four of these are the responsibility of Form classes.
    Typically, you will create one Form subclass for each form in your
    application.  Thanks to the separation of responsibilities here,
    it's not too hard to structure things so that a given form is
    rendered and/or processed somewhat differently depending on context.
    That separation is as follows:
      * the constructor declares what widgets are in the form, and
        any static text that is always associated with those widgets
        (in particular, a widget title and "hint" text)
      * the 'render()' method combines the widgets and their associated
        text to create a (1-D) stream of HTML that represents the
        (2-D) web page that will be presented to the user
      * the 'process()' method parses the user input values from the form
        and validates them
      * the 'action()' method takes care of finishing whatever action
        was requested by the user submitting the form -- commit
        a database transaction, update session flags, redirect the
        user to a new page, etc.

    This class provides a default 'process()' method that just parses
    each widget, storing any error messages for display on the next
    'render()', and returns the results (if the form parses
    successfully) in a dictionary.

    This class also provides a default 'render()' method that lays out
    widgets and text in a 3-column table: the first column is the widget
    title, the second column is the widget itself, and the third column is
    any hint and/or error text associated with the widget.  Also provided
    are methods that can be used to construct this table a row at a time,
    so you can use this layout for most widgets, but escape from it for
    oddities.

    Instance attributes:
      widgets : { widget_name:string : widget:Widget }
        dictionary of all widgets in the form
      widget_order : [Widget]
        same widgets as 'widgets', but ordered (because order matters)
      submit_buttons : [SubmitButtonWidget]
        the submit button widgets in the form

      error : { widget_name:string : error_message:string }
      hint : { widget_name:string : hint_text:string }
      title : { widget_name:string : widget_title:string }
      required : { widget_name:string : boolean }

    """

    TOKEN_NAME = "_form_id" # name of hidden token widget

    def __init__(self, method="post", enctype=None, use_tokens=1):

        if method not in ("post", "get"):
            raise ValueError("Form method must be 'post' or 'get', "
                             "not %r" % method)
        self.method = method

        if enctype is not None and enctype not in (
            "application/x-www-form-urlencoded", "multipart/form-data"):
            raise ValueError("Form enctype must be "
                               "'application/x-www-form-urlencoded' or "
                               "'multipart/form-data', not %r" % enctype)
        self.enctype = enctype

        # The first major component of a form: its widgets.  We want
        # both easy access and order, so we have a dictionary and a list
        # of the same objects.  The dictionary is keyed on widget name.
        # These are populated by the 'add_*_widget()' methods.
        self.widgets = {}
        self.widget_order = []
        self.submit_buttons = []
        self.cancel_url = None

        # The second major component: text.  It's up to the 'render()'
        # method to figure out how to lay these out; the standard
        # 'render()' does so in a fairly sensible way that should work
        # for most of our forms.  These are also populated by the
        # 'add_*_widget()' methods.
        self.error = {}
        self.hint = {}
        self.title = {}
        self.required = {}

        config = get_publisher().config
        if self.method == "post" and use_tokens and config.form_tokens:
            # unique token for each form, this prevents many cross-site
            # attacks and prevents a form from being submitted twice
            self.add_widget(FormTokenWidget, self.TOKEN_NAME)
            self.use_form_tokens = 1
        else:
            self.use_form_tokens = 0

        # Subclasses should override this method to specify the actual
        # widgets in this form -- typically this consists of a series of
        # calls to 'add_widget()', which updates the data structures we
        # just defined.


    # -- Layout (rendering) methods ------------------------------------

    # The third major component of a web form is layout.  These methods
    # combine text and widgets in a 1-D stream of HTML, or in a 2-D web
    # page (depending on your level of abstraction).

    def render(self, request, action_url):
        # render(request : HTTPRequest,
        #           action_url : string)
        #    -> HTML text
        #
        # Render a form as HTML.
        assert type(action_url) in (StringType, htmltext)
        r = TemplateIO(html=1)
        r += self._render_start(request, action_url,
                                enctype=self.enctype, method=self.method)
        r += self._render_body(request)
        r += self._render_finish(request)
        return r.getvalue()

    def _render_start(self, request, action,
                      enctype=None, method='post', name=None):
        r = TemplateIO(html=1)
        r += htmltag('form', enctype=enctype, method=method,
                     action=action, name=name)
        r += self._render_hidden_widgets(request)
        return r.getvalue()

    def _render_finish(self, request):
        r = TemplateIO(html=1)
        r += htmltext('</form>')
        r += self._render_javascript(request)
        return r.getvalue()

    def _render_sep(self, text, line=1):
        return htmltext('<tr><td colspan="3">%s<strong><big>%s'
                        '</big></strong></td></tr>') % \
                                      (line and htmltext('<hr>') or '', text)

    def _render_error(self, error):
        if error:
            return htmltext('<font color="red">%s</font><br />') % nl2br(error)
        else:
            return ''

    def _render_hint(self, hint):
        if hint:
            return htmltext('<em>%s</em>') % hint
        else:
            return ''

    def _render_widget_row(self, request, widget):
        if widget.widget_type == 'hidden':
            return ''
        title = self.title[widget.name] or ''
        if self.required.get(widget.name):
            title = title + htmltext('&nbsp;*')
        r = TemplateIO(html=1)
        r += htmltext('<tr><th colspan="3" align="left">')
        r += title
        r += htmltext('</th></tr>'
                      '<tr><td>&nbsp;&nbsp;</td><td>')
        r += widget.render(request)
        r += htmltext('</td><td>')
        r += self._render_error(self.error.get(widget.name))
        r += self._render_hint(self.hint.get(widget.name))
        r += htmltext('</td></tr>')
        return r.getvalue()

    def _render_hidden_widgets(self, request):
        r = TemplateIO(html=1)
        for widget in self.widget_order:
            if widget.widget_type == 'hidden':
                r += widget.render(request)
                r += self._render_error(self.error.get(widget.name))
        return r.getvalue()

    def _render_submit_buttons(self, request, ncols=3):
        r = TemplateIO(html=1)
        r += htmltext('<tr><td colspan="%d">\n') % ncols
        for button in self.submit_buttons:
            r += button.render(request)
        r += htmltext('</td></tr>')
        return r.getvalue()

    def _render_visible_widgets(self, request):
        r = TemplateIO(html=1)
        for widget in self.widget_order:
            r += self._render_widget_row(request, widget)
        return r.getvalue()

    def _render_error_notice(self, request):
        if self.error:
            r = htmltext('<tr><td colspan="3">'
                         '<font color="red"><strong>Warning:</strong></font> '
                         'there were errors processing your form.  '
                         'See below for details.'
                         '</td></tr>')
        else:
            r = ''
        return r

    def _render_required_notice(self, request):
        if any(self.required.values()):
            r = htmltext('<tr><td colspan="3">'
                         '<b>*</b> = <em>required field</em>'
                         '</td></tr>')
        else:
            r = ''
        return r

    def _render_body(self, request):
        r = TemplateIO(html=1)
        r += htmltext('<table>')
        r += self._render_error_notice(request)
        r += self._render_required_notice(request)
        r += self._render_visible_widgets(request)
        r += self._render_submit_buttons(request)
        r += htmltext('</table>')
        return r.getvalue()

    def _render_javascript(self, request):
        """Render javacript code for the form, if any.
           Insert code lexically sorted by code_id
        """
        javascript_code = request.response.javascript_code
        if javascript_code:
            form_code = []
            code_ids = sorted(javascript_code.keys())
            for code_id in code_ids:
                code = javascript_code[code_id]
                if code:
                    form_code.append(code)
                    javascript_code[code_id] = ''
            if form_code:
                return JAVASCRIPT_MARKUP % htmltext(''.join(form_code))
        return ''


    # -- Processing methods --------------------------------------------

    # The fourth and final major component: code to process the form.
    # The standard 'process()' method just parses every widget and
    # returns a { field_name : field_value } dictionary as 'values'.

    def process(self, request):
        """process(request : HTTPRequest) -> values : { string : any }

        Process the form data, validating all input fields (widgets).
        If any errors in input fields, adds error messages to the
        'error' attribute (so that future renderings of the form will
        include the errors).  Returns a dictionary mapping widget names to
        parsed values.
        """
        self.error.clear()

        values = {}
        for widget in self.widget_order:
            try:
                val = widget.parse(request)
            except FormValueError as exc:
                self.error[widget.name] = exc.msg
            else:
                values[widget.name] = val

        return values

    def action(self, request, submit, values):
        """action(request : HTTPRequest, submit : string,
                  values : { string : any }) -> string

        Carry out the action required by a form submission.  'submit' is the
        name of submit button used to submit the form.  'values' is the
        dictionary of parsed values from 'process()'.  Note that error
        checking cannot be done here -- it must done in the 'process()'
        method.
        """
        raise NotImplementedError("sub-classes must implement 'action()'")

    def handle(self, request):
        """handle(request : HTTPRequest) -> string

        Master method for handling forms.  It should be called after
        initializing a form.  Controls form action based on a request.  You
        probably should override 'process' and 'action' instead of
        overriding this method.
        """
        action_url = self.get_action_url(request)
        if not self.form_submitted(request):
            return self.render(request, action_url)
        submit = self.get_submit_button(request)
        if submit == "cancel":
            return redirect(self.cancel_url)
        values = self.process(request)
        if submit == "":
            # The form was submitted by unknown submit button, assume that
            # the submission was required to update the layout of the form.
            # Clear the errors and re-render the form.
            self.error.clear()
            return self.render(request, action_url)

        if self.use_form_tokens:
            # before calling action() ensure that there is a valid token
            # present
            token = values.get(self.TOKEN_NAME)
            if not request.session.has_form_token(token):
                if not self.error:
                    # if there are other errors then don't show the token
                    # error, the form needs to be resubmitted anyhow
                    self.error[self.TOKEN_NAME] = (
                           "The form you have submitted is invalid.  It has "
                           "already been submitted or has expired. Please "
                           "review and resubmit the form.")
            else:
                request.session.remove_form_token(token)

        if self.error:
            return self.render(request, action_url)
        else:
            return self.action(request, submit, values)


    # -- Convenience methods -------------------------------------------

    def form_submitted(self, request):
        """form_submitted(request : HTTPRequest) -> boolean

        Return true if a form was submitted in the current request.
        """
        return len(request.form) > 0

    def get_action_url(self, request):
        action_url = url_quote(request.get_path())
        query = request.get_environ("QUERY_STRING")
        if query:
            action_url += "?" + query
        return action_url

    def get_submit_button(self, request):
        """get_submit_button(request : HTTPRequest) -> string | None

        Get the name of the submit button that was used to submit the
        current form.  If the browser didn't include this information in
        the request, use the first submit button registered.
        """
        for button in self.submit_buttons:
            if button.name in request.form:
                return button.name
        else:
            if request.form and self.submit_buttons:
                return ""
            else:
                return None

    def get_widget(self, widget_name):
        return self.widgets.get(widget_name)

    def parse_widget(self, name, request):
        """parse_widget(name : string, request : HTTPRequest) -> any

        Parse the value of named widget.  If any parse errors, store the
        error message (in self.error) for use in the next rendering of
        the form and return None; otherwise, return the value parsed
        from the widget (whose type depends on the widget type).
        """
        try:
            return self.widgets[name].parse(request)
        except FormValueError as exc:
            self.error[name] = str(exc)
            return None

    def store_value(self, widget_name, request, target,
                    mode="modifier",
                    key=None,
                    missing_error=None):
        """store_value(widget_name : string,
                       request : HTTPRequest,
                       target : instance | dict,
                       mode : string = "modifier",
                       key : string = widget_name,
                       missing_error : string = None)

        Parse a widget and, if it parsed successfully, store its value
        in 'target'.  The value is stored in 'target' by name 'key';
        if 'key' is not supplied, it defaults to 'widget_name'.
        How the value is stored depends on 'mode':
          * modifier: call a modifier method, eg. if 'key' is "foo",
            call 'target.set_foo(value)'
          * direct: direct attribute update, eg. if 'key' is
            "foo" do "target.foo = value"
          * dict: dictionary update, eg. if 'key' is "foo" do
            "target['foo'] = value"

        If 'missing_error' is supplied, use it as an error message if
        the field doesn't have a value -- ie. supplying 'missing_error'
        means this field is required.
        """
        value = self.parse_widget(widget_name, request)
        if (value is None or value == "") and missing_error:
            self.error[widget_name] = missing_error
            return None

        if key is None:
            key = widget_name
        if mode == "modifier":
            # eg. turn "name" into "target.set_name", and
            # call it like "target.set_name(value)"
            mod = getattr(target, "set_" + key)
            mod(value)
        elif mode == "direct":
            if not hasattr(target, key):
                raise AttributeError("target object %s doesn't have attribute %s" %
                       (repr(target), key))
            setattr(target, key, value)
        elif mode == "dict":
            target[key] = value
        else:
            raise ValueError("unknown update mode %s" % repr(mode))

    def clear_widget(self, widget_name):
        self.widgets[widget_name].clear()

    def get_widget_value(self, widget_name):
        return self.widgets[widget_name].value

    def set_widget_value(self, widget_name, value):
        self.widgets[widget_name].set_value(value)


    # -- Form population methods ---------------------------------------

    def add_widget(self, widget_type, name, value=None,
                   title=None, hint=None, required=0, **args):
        """add_widget(widget_type : string | Widget,
                      name : string,
                      value : any = None,
                      title : string = None,
                      hint : string = None,
                      required : boolean = 0,
                      ...) -> Widget

        Create a new Widget object and add it to the form.  The widget
        class used depends on 'widget_type', and the expected type of
        'value' also depends on the widget class.  Any extra keyword
        args are passed to the widget constructor.

        Returns the new Widget.
        """
        if name in self.widgets:
            raise ValueError("form already has '%s' variable" % name)
        klass = get_widget_class(widget_type)
        new_widget = klass(*(name, value), **args)

        self.widgets[name] = new_widget
        self.widget_order.append(new_widget)
        self.title[name] = title
        self.hint[name] = hint
        self.required[name] = required
        return new_widget

    def add_submit_button(self, name, value):
        global _widget_class
        if name in self.widgets:
            raise ValueError("form already has '%s' variable" % name)
        new_widget = _widget_class['submit_button'](name, value)

        self.widgets[name] = new_widget
        self.submit_buttons.append(new_widget)

    def add_cancel_button(self, caption, url):
        if not isinstance(url, (StringType, htmltext)):
            raise TypeError("url must be a string (got %r)" % url)
        self.add_submit_button("cancel", caption)
        self.cancel_url = url

# class Form


_widget_class = {}

def register_widget_class(klass, widget_type=None):
    global _widget_class
    if widget_type is None:
        widget_type = klass.widget_type
    assert widget_type is not None, "widget_type must be defined"
    _widget_class[widget_type] = klass

def get_widget_class(widget_type):
    global _widget_class
    if hasattr(widget_type, '__call__'):
        # Presumably someone passed a widget class object to
        # Widget.create_subwidget() or Form.add_widget() --
        # don't bother with the widget class registry at all.
        return widget_type
    else:
        try:
            return _widget_class[widget_type]
        except KeyError:
            raise ValueError("unknown widget type %r" % widget_type)
