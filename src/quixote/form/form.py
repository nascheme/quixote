"""HTML forms built from Widget objects.

A `Form` collects a set of `Widget` instances, renders
them as an HTML ``<form>``, and -- on submission -- parses the request data
back into Python values.  A typical handler builds the form, adds widgets,
and branches on whether it was submitted without errors::

    form = Form()
    form.add_string('name', title='Your name', required=True)
    form.add_submit('go', 'Continue')
    if form.is_submitted() and not form.has_errors():
        name = form['name']
        ...            # act on the input, usually redirect
    return form.render()

When form tokens are enabled (see the ``FORM_TOKENS`` config setting), a
hidden token widget is added automatically to guard against cross-site
request forgery and double submission.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, TypeVar

from quixote import get_publisher, get_request, get_session
from quixote.form.widget import (
    CheckboxWidget,
    FloatWidget,
    HiddenWidget,
    IntWidget,
    MultipleSelectWidget,
    PasswordWidget,
    RadiobuttonsWidget,
    Rendered,
    ResetWidget,
    SingleSelectWidget,
    StringWidget,
    SubmitWidget,
    TextWidget,
    Widget,
)
from quixote.html import TemplateIO, htmltag, htmltext

if TYPE_CHECKING:
    from quixote.http_request import HTTPRequest

_T = TypeVar('_T')


class FormTokenWidget(HiddenWidget):
    """Hidden widget carrying a per-form anti-CSRF token.

    Added automatically by `Form` when form tokens are enabled.  On render it
    creates a fresh token in the session; on parse it checks the submitted
    token against the session and consumes it, so a given form can only be
    submitted once.  A missing or unknown token produces a (non-displayed)
    error that `Form._render_error_notice` turns into the "invalid form"
    notice.
    """

    def _parse(self, request: HTTPRequest) -> None:
        token = request.form.get(self.name)
        session = get_session()
        assert session is not None
        if not isinstance(token, str) or not session.has_form_token(token):
            self.error = 'invalid'  # this error does not get displayed
        else:
            session.remove_form_token(token)

    def render_error(self, error: object) -> Rendered:
        return ''

    def render(self) -> Rendered:
        session = get_session()
        assert session is not None
        self.value = session.create_form_token()
        return HiddenWidget.render(self)


class Form(object):
    """A collection of widgets rendered and processed as one HTML form.

    Construct a `Form`, populate it with the ``add_*`` methods (or `add` for
    an arbitrary widget class), then use `is_submitted` / `has_errors` to
    decide whether to act on the input and `render` to emit the HTML.  Parsed
    widget values are read with ``form[name]`` or `get`.  Applications
    commonly subclass `Form` to add domain-specific widgets or override
    rendering.

    Widgets are sorted as they are added: submit buttons go in
    `submit_widgets` (rendered at the end), hidden fields in `hidden_widgets`
    (rendered at the start), and everything else in `widgets`.

    Instance attributes:
      method : string
        HTTP method, "post" (default) or "get".
      action : object
        form action URL; defaults to the current request's query string.
      enctype : string | None
        form encoding; must be "multipart/form-data" for file uploads.
      widgets : [Widget]
        widgets that are not submit or hidden widgets.
      submit_widgets : [SubmitWidget]
        submit buttons, rendered at the end of the form.
      hidden_widgets : [HiddenWidget]
        hidden fields, rendered at the start of the form.
      attrs : {string: any}
        extra attributes for the ``<form>`` tag.
    """

    TOKEN_NAME = "_form_id"  # name of hidden token widget

    method: str
    action: object
    attrs: dict[str, Any]
    widgets: list[Widget]
    submit_widgets: list[SubmitWidget]
    hidden_widgets: list[HiddenWidget]
    _names: dict[str, Widget]
    enctype: str | None

    JAVASCRIPT_MARKUP = htmltext(
        '<script type="text/javascript">\n<!--\n%s\n// -->\n</script>\n'
    )

    TOKEN_NOTICE = htmltext(
        '<div class="errornotice">'
        'The form you have submitted is invalid.  Most '
        'likely it has been successfully submitted once '
        'already.  Please review the the form data '
        'and submit the form again.'
        '</div>'
    )

    ERROR_NOTICE = htmltext(
        '<div class="errornotice">'
        'There were errors processing your form.  '
        'See below for details.'
        '</div>'
    )

    def __init__(
        self,
        method: str = "post",
        action: object | None = None,
        enctype: str | None = None,
        use_tokens: bool = True,
        **attrs: Any,
    ) -> None:
        """Create an empty form.

        `method` is "post" or "get".  `action` is the submission URL and
        defaults to the current query string.  `enctype` must be set to
        "multipart/form-data" when the form contains a file upload.  When
        `use_tokens` is true and the method is "post", a `FormTokenWidget` is
        added automatically if the ``FORM_TOKENS`` config setting is enabled.
        Remaining keyword arguments become attributes of the ``<form>`` tag.
        """
        if method not in ("post", "get"):
            raise ValueError(
                "Form method must be 'post' or 'get', not %r" % method
            )
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
            "application/x-www-form-urlencoded",
            "multipart/form-data",
        ):
            raise ValueError(
                "Form enctype must be "
                "'application/x-www-form-urlencoded' or "
                "'multipart/form-data', not %r" % enctype
            )
        self.enctype = enctype

        if use_tokens and self.method == "post":
            config = get_publisher().config
            if config.form_tokens:
                # unique token for each form, this prevents many cross-site
                # attacks and prevents a form from being submitted twice
                self.add(FormTokenWidget, self.TOKEN_NAME, value=None)

    def _get_default_action(self) -> str:
        query = get_request().get_query()
        if query:
            return "?" + query
        else:
            return ""

    # -- Form data access methods --------------------------------------

    def __getitem__(self, name: str) -> object | None:
        """Return the parsed value of the named widget.

        Raises KeyError if there is no widget named `name`.  Use `get` to
        supply a default instead.
        """
        try:
            return self._names[name].parse()
        except KeyError:
            raise KeyError('no widget named %r' % name)

    def __contains__(self, name: object) -> bool:
        """Return true if the widget named 'name' is in the form."""
        return name in self._names

    def get(self, name: str, default: _T | None = None) -> object | _T | None:
        """Return the parsed value of the named widget, or `default`.

        Like ``form[name]`` but returns `default` when no widget named `name`
        exists instead of raising KeyError.
        """
        widget = self._names.get(name)
        if widget is not None:
            return widget.parse()
        else:
            return default

    def get_widget(self, name: str) -> Widget | None:
        """Return the widget named `name`, or None if it does not exist.

        Use this to reach a widget object directly, e.g. to set options on a
        select widget or read its error.
        """
        return self._names.get(name)

    def get_submit_widgets(self) -> list[SubmitWidget]:
        """Return the list of submit-button widgets in the form."""
        return self.submit_widgets

    def get_all_widgets(self) -> list[Widget]:
        """Return every widget added to the form.

        Includes submit and hidden widgets but not sub-widgets nested inside a
        `CompositeWidget`.
        """
        return list(self._names.values())

    # -- Form processing and error checking ----------------------------

    def is_submitted(self) -> bool:
        """Return true if this form was submitted in the current request.

        A "post" form counts as submitted only when the request method is
        actually POST.  A "get" form counts as submitted whenever the request
        carries any form data.  Note this does not check for errors -- combine
        with `has_errors` before acting on the input.
        """
        request = get_request()
        if self.method == 'post':
            if request.get_method() == 'POST':
                return True
            else:
                return False
        else:
            return bool(request.form)

    def has_errors(self) -> bool:
        """Parse all widgets and return true if any has an error.

        Forces every widget to parse its submitted value (so validation runs)
        and reports whether any widget flagged an error.  Returns false when
        the form was not submitted.
        """
        request = get_request()
        has_errors = False
        if self.is_submitted():
            for widget in self.get_all_widgets():
                if widget.has_error(request=request):
                    has_errors = True
        return has_errors

    def clear_errors(self) -> None:
        """Ensure that all components of the form have parsed themselves.
        Clear any errors that might have occured during parsing.
        """
        request = get_request()
        for widget in self.get_all_widgets():
            widget.clear_error(request)

    def force_value(self, name: str, value: object | None) -> None:
        """Force the value of a widget to be 'value', even if the form
        has been submitted and a different value is in the request form data.
        """
        widget = self.get_widget(name)
        if widget is None:
            raise ValueError('unknown widget %r' % name)
        widget.clear_error()  # calls parse internally
        widget.set_value(value)

    def get_submit(self) -> str | bool:
        """Return which submit button was used, if any.

        Returns the name of the `SubmitWidget` that submitted the form.  If
        the form was submitted but not through a known submit widget, returns
        True; if it was not submitted at all, returns False.  Handy for
        dispatching when a form has several submit buttons.
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

    def set_error(self, name: str, error: str | None) -> None:
        """Set an error message on the named widget.

        Use this for validation that cannot be expressed on the widget itself,
        e.g. checking one field against another.  A widget with an error is
        rendered with its message and makes `has_errors` return true.  Raises
        KeyError if there is no widget named `name`.
        """
        widget = self._names.get(name)
        if not widget:
            raise KeyError("unknown name %r" % name)
        widget.set_error(error)

    # -- Form population methods ---------------------------------------

    def add(
        self,
        widget_class: type[Widget],
        name: str,
        *args: Any,
        **kwargs: Any,
    ) -> None:
        """Add a widget of `widget_class` to the form under `name`.

        `name` must be unique within the form and becomes the widget's HTML
        name and default ``id``.  Extra positional and keyword arguments are
        passed to the widget constructor (``value``, ``title``, ``hint``,
        ``required``, ``options``, and so on).  The convenience ``add_*``
        methods wrap this for the common widget types.  Raises ValueError if
        `name` is already in use.
        """
        if name in self._names:
            raise ValueError("form already has '%s' widget" % name)
        # add 'id' attribute if not already present
        if 'id' not in kwargs:
            kwargs['id'] = name
        kwargs['form'] = self
        widget = widget_class(name, *args, **kwargs)
        self._names[name] = widget
        if isinstance(widget, SubmitWidget):
            self.submit_widgets.append(widget)  # will be rendered at end
        elif isinstance(widget, HiddenWidget):
            self.hidden_widgets.append(widget)  # will be render at beginning
        else:
            self.widgets.append(widget)

    # convenience methods

    def add_submit(
        self,
        name: str,
        value: object | None = None,
        **kwargs: Any,
    ) -> None:
        """Add a submit button; `value` is the button label."""
        self.add(SubmitWidget, name, value, **kwargs)

    def add_reset(
        self,
        name: str,
        value: object | None = None,
        **kwargs: Any,
    ) -> None:
        """Add a reset button; `value` is the button label."""
        self.add(ResetWidget, name, value, **kwargs)

    def add_hidden(
        self,
        name: str,
        value: object | None = None,
        **kwargs: Any,
    ) -> None:
        """Add a hidden field carrying `value` through the round-trip."""
        self.add(HiddenWidget, name, value, **kwargs)

    def add_string(
        self,
        name: str,
        value: object | None = None,
        **kwargs: Any,
    ) -> None:
        """Add a single-line text input (StringWidget)."""
        self.add(StringWidget, name, value, **kwargs)

    def add_text(
        self,
        name: str,
        value: object | None = None,
        **kwargs: Any,
    ) -> None:
        """Add a multi-line text area (TextWidget)."""
        self.add(TextWidget, name, value, **kwargs)

    def add_password(
        self,
        name: str,
        value: object | None = None,
        **kwargs: Any,
    ) -> None:
        """Add a password input (PasswordWidget)."""
        self.add(PasswordWidget, name, value, **kwargs)

    def add_checkbox(
        self,
        name: str,
        value: object | None = None,
        **kwargs: Any,
    ) -> None:
        """Add a checkbox with a boolean value (CheckboxWidget)."""
        self.add(CheckboxWidget, name, value, **kwargs)

    def add_single_select(
        self,
        name: str,
        value: object | None = None,
        **kwargs: Any,
    ) -> None:
        """Add a single-selection dropdown (`SingleSelectWidget`).

        Pass ``options=`` to supply the choices.
        """
        self.add(SingleSelectWidget, name, value, **kwargs)

    def add_multiple_select(
        self,
        name: str,
        value: object | None = None,
        **kwargs: Any,
    ) -> None:
        """Add a multiple-selection list (`MultipleSelectWidget`).

        Pass ``options=`` to supply the choices.
        """
        self.add(MultipleSelectWidget, name, value, **kwargs)

    def add_radiobuttons(
        self,
        name: str,
        value: object | None = None,
        **kwargs: Any,
    ) -> None:
        """Add a radio-button group (`RadiobuttonsWidget`).

        Pass ``options=`` to supply the choices.
        """
        self.add(RadiobuttonsWidget, name, value, **kwargs)

    def add_float(
        self,
        name: str,
        value: float | None = None,
        **kwargs: Any,
    ) -> None:
        """Add a text input that parses to a float (FloatWidget)."""
        self.add(FloatWidget, name, value, **kwargs)

    def add_int(
        self,
        name: str,
        value: int | None = None,
        **kwargs: Any,
    ) -> None:
        """Add a text input that parses to an int (IntWidget)."""
        self.add(IntWidget, name, value, **kwargs)

    # -- Layout (rendering) methods ------------------------------------

    def render(self) -> Rendered:
        """Render the whole form as HTML (returns htmltext).

        Emits the ``<form>`` tag, hidden widgets, an error notice if the form
        has errors, the visible widgets, and the submit buttons.  This is the
        value a handler normally returns for the page body.
        """
        r = TemplateIO(html=True)
        r += self._render_start()
        r += self._render_body()
        r += self._render_finish()
        return r.getvalue()

    def _render_start(self) -> Rendered:
        r = TemplateIO(html=True)
        r += htmltag(
            'form',
            method=self.method,
            enctype=self.enctype,
            action=self.action,
            **self.attrs,
        )
        r += self._render_hidden_widgets()
        return r.getvalue()

    def _render_finish(self) -> Rendered:
        r = TemplateIO(html=True)
        r += htmltext('</form><br class="quixoteform" />')
        code = get_request().response.javascript_code
        if code:
            r += self._render_javascript(code)
        return r.getvalue()

    def _render_widgets(self) -> Rendered:
        r = TemplateIO(html=True)
        for widget in self.widgets:
            r += widget.render()
        return r.getvalue()

    def _render_hidden_widgets(self) -> Rendered:
        r = TemplateIO(html=True)
        for widget in self.hidden_widgets:
            r += widget.render()
        return r.getvalue()

    def _render_submit_widgets(self) -> Rendered:
        r = TemplateIO(html=True)
        if self.submit_widgets:
            r += htmltext('<div class="submit">')
            for widget in self.submit_widgets:
                r += widget.render()
            r += htmltext('</div><br class="submit" />')
        return r.getvalue()

    def _render_error_notice(self) -> Rendered:
        token_widget = self.get_widget(self.TOKEN_NAME)
        if token_widget is not None and token_widget.has_error():
            # form tokens are enabled but the token data in the request
            # does not match anything in the session.  It could be an
            # a cross-site attack but most likely the back button has
            # be used
            return self.TOKEN_NOTICE
        else:
            return self.ERROR_NOTICE

    def _render_javascript(
        self,
        javascript_code: dict[str, str],
    ) -> Rendered:
        """Render javacript code for the form.  Insert code lexically
        sorted by code_id.
        """
        form_code: list[str] = []
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

    def _render_body(self) -> Rendered:
        r = TemplateIO(html=True)
        if self.has_errors():
            r += self._render_error_notice()
        r += self._render_widgets()
        r += self._render_submit_widgets()
        return r.getvalue()
