"""Provides the basic web widget classes: Widget itself, plus StringWidget,
TextWidget, CheckboxWidget, etc.
"""

from __future__ import annotations

import struct
from collections.abc import Mapping, Sequence
from typing import TYPE_CHECKING, Any

from quixote import current_request
from quixote.html import TemplateIO, htmlescape, htmltag, htmltext, stringify
from quixote.http_request import Upload

if TYPE_CHECKING:
    from quixote.form.form import Form
    from quixote.http_request import HTTPRequest

type Attrs = Mapping[str, Any]
type Rendered = str | htmltext
type Option = tuple[object, object, str]


def subname(prefix: str, name: str) -> str:
    """Create a unique name for a sub-widget or sub-component."""
    # $ is nice because it's valid as part of a Javascript identifier
    return "%s$%s" % (prefix, name)


def merge_attrs(
    base: Attrs | None,
    overrides: Attrs | None,
) -> dict[str, Any]:
    """({string: any}, {string: any}) -> {string: any}"""
    items: list[tuple[str, Any]] = []
    if base:
        items.extend(base.items())
    if overrides:
        items.extend(overrides.items())
    attrs = {}
    for name, val in items:
        if name.endswith('_'):
            name = name[:-1]
        attrs[name] = val
    return attrs


class WidgetValueError(Exception):
    """Raised by a widget's parse step to reject an invalid value.

    Raise this from a ``_parse`` override to signal bad input; the widget
    catches it and turns its message into the widget's displayed error.
    """

    msg: object

    def __init__(self, msg: object) -> None:
        self.msg = msg

    def __str__(self) -> str:
        return stringify(self.msg)


class Widget(object):
    """Abstract base for form widgets -- one HTML control plus its value.

    A widget owns a form field: its `name`, its current `value`, and any
    validation `error`.  Its life cycle has two halves.  On the way in,
    `parse` reads the submitted value out of the request, coerces it to the
    widget's Python type, and records an error if it is invalid or a required
    field is missing (parsing happens once and is cached).  On the way out,
    `render` produces the HTML: title, the control itself (`render_content`,
    supplied by each concrete subclass), hint, and error message.

    Widgets are usually created through `Form.add` rather than directly.
    Read attributes directly, but set them through the ``set_*`` methods so
    parsing state stays consistent.

    Instance attributes:
      name : string
        HTML control name; unique within its form.
      value : any
        the widget's value -- the parsed submission, or the initial value.
      error : string | None
        validation error message, or None.
      title : any
        label shown above the control.
      hint : any
        help text shown near the control.
      required : bool
        if true, an empty submission is flagged as an error.
      attrs : {string: any}
        extra attributes for the rendered HTML tag.
    """

    REQUIRED_ERROR = 'required'

    name: str
    value: object | None
    error: str | None
    title: object
    hint: object
    required: bool
    render_br: bool
    attrs: dict[str, Any]
    _form: Form | None
    _parsed: bool

    def __init__(
        self,
        name: str,
        value: object | None = None,
        title: object = "",
        hint: object = "",
        required: bool = False,
        render_br: bool = True,
        form: Form | None = None,
        attrs: Attrs | None = None,
        **kwattrs: Any,
    ) -> None:
        assert self.__class__ is not Widget, "abstract class"
        self.name = name
        self.value = value
        self.error = None
        self.title = title
        self.hint = hint
        self.required = required
        self.render_br = render_br
        self.attrs = merge_attrs(attrs, kwattrs)
        self._form = form
        self._parsed = False

    def __repr__(self) -> str:
        return "<%s at %x: %s>" % (
            self.__class__.__name__,
            id(self),
            self.name,
        )

    def __str__(self) -> str:
        return "%s: %s" % (self.__class__.__name__, self.name)

    def get_name(self) -> str:
        """Return the widget's HTML control name."""
        return self.name

    def set_value(self, value: object | None) -> None:
        """Set the widget's value, overriding any submitted value."""
        self.value = value

    def set_error(self, error: str | None) -> None:
        """Set (or clear, with None) the widget's validation error."""
        self.error = error

    def get_error(self, request: HTTPRequest | None = None) -> str | None:
        """Parse the widget and return its error message, or None.

        Triggers parsing (so validation runs) before returning the error.
        """
        self.parse(request=request)
        return self.error

    def has_error(self, request: HTTPRequest | None = None) -> bool:
        """Return true if the widget has a validation error (parses first)."""
        return bool(self.get_error(request=request))

    def clear_error(self, request: HTTPRequest | None = None) -> None:
        """Parse the widget, then discard any error it produced."""
        self.parse(request=request)
        self.error = None

    def set_title(self, title: object) -> None:
        """Set the label shown above the control."""
        self.title = title

    def get_title(self) -> object:
        """Return the widget's title (label)."""
        return self.title

    def set_hint(self, hint: object) -> None:
        """Set the help text shown near the control."""
        self.hint = hint

    def get_hint(self) -> object:
        """Return the widget's hint (help text)."""
        return self.hint

    def is_required(self) -> bool:
        """Return true if an empty submission is treated as an error."""
        return self.required

    def parse(self, request: HTTPRequest | None = None) -> object | None:
        """Parse the submitted value from the request and return it.

        Reads the raw field, coerces it to the widget's type, and sets an
        error for an invalid value or a missing required field.  Runs at most
        once per widget (the result is cached); does nothing and returns the
        initial value when the form was not submitted.  `request` defaults to
        the current request.
        """
        if not self._parsed:
            self._parsed = True
            if request is None:
                request = current_request()
            if self._form is not None:
                # use the form to determine if form data was submitted.  It
                # is possible that there is a query string, the request method
                # is GET and the form method is POST.  In that case the form
                # should not be considered submitted.
                submitted = self._form.is_submitted()
            else:
                submitted = request.form or request.get_method() == 'POST'
            if submitted:
                try:
                    self._parse(request)
                except WidgetValueError as exc:
                    self.set_error(stringify(exc))
                if (
                    self.required
                    and self.value is None
                    and not self.has_error()
                ):
                    self.set_error(self.REQUIRED_ERROR)
        return self.value

    def _parse(self, request: HTTPRequest) -> None:
        # subclasses may override but this is not part of the public API
        value = request.form.get(self.name)
        if isinstance(value, str) and value.strip():
            self.value = value
        else:
            self.value = None

    def render_title(self, title: object) -> Rendered:
        """Render the title block, marking required fields with a ``*``."""
        if title:
            if self.required:
                title = htmlescape(title) + htmltext(
                    '<span class="required">*</span>'
                )
            return htmltext('<div class="title">%s</div>') % title
        else:
            return ''

    def render_hint(self, hint: object) -> Rendered:
        """Render the hint block, or empty text when there is no hint."""
        if hint:
            return htmltext('<div class="hint">%s</div>') % hint
        else:
            return ''

    def render_error(self, error: object) -> Rendered:
        """Render the error block, or empty text when there is no error."""
        if error:
            return htmltext('<div class="error">%s</div>') % error
        else:
            return ''

    def render(self) -> Rendered:
        """Render the complete widget: title, control, hint, and error.

        Wraps `render_content` (the control itself) with the surrounding
        title, hint, and error markup.  Subclasses usually override
        `render_content` rather than this method.
        """
        r = TemplateIO(html=True)
        classnames = '%s widget' % self.__class__.__name__
        r += htmltext('<div class="%s">') % classnames
        r += self.render_title(self.get_title())
        r += htmltext('<div class="content">')
        r += self.render_content()
        r += self.render_hint(self.get_hint())
        r += self.render_error(self.get_error())
        r += htmltext('</div>')
        r += htmltext('</div>')
        if self.render_br:
            r += htmltext('<br class="%s" />') % classnames
        r += htmltext('\n')
        return r.getvalue()

    def render_content(self) -> Rendered:
        """Render just the HTML control for this widget.

        Abstract -- each concrete widget subclass implements this to emit its
        input, select, textarea, and so on.  `render` wraps the result with
        the title, hint, and error decoration.
        """
        raise NotImplementedError


# class Widget

# -- Fundamental widget types ------------------------------------------
# These correspond to the standard types of input tag in HTML:
#   text     StringWidget
#   password PasswordWidget
#   radio    RadiobuttonsWidget
#   checkbox CheckboxWidget
#
# and also to the other basic form elements:
#   <textarea>  TextWidget
#   <select>    SingleSelectWidget
#   <select multiple>
#               MultipleSelectWidget


class StringWidget(Widget):
    """Widget for entering a single string: corresponds to
    '<input type="text">' in HTML.

    Instance attributes:
      value : string
    """

    # This lets PasswordWidget be a trivial subclass
    HTML_TYPE = "text"

    def render_content(self) -> Rendered:
        return htmltag(
            "input",
            xml_end=True,
            type=self.HTML_TYPE,
            name=self.name,
            value=self.value,
            **self.attrs,
        )


class FileWidget(StringWidget):
    """Subclass of StringWidget for uploading files.

    Instance attributes: none
    """

    HTML_TYPE = "file"

    def _parse(self, request: HTTPRequest) -> None:
        parsed_value = request.form.get(self.name)
        if isinstance(parsed_value, Upload):
            self.value = parsed_value
        else:
            self.value = None


class PasswordWidget(StringWidget):
    """Trivial subclass of StringWidget for entering passwords (different
    widget type because HTML does it that way).

    Instance attributes: none
    """

    HTML_TYPE = "password"


class TextWidget(Widget):
    """Widget for entering a long, multi-line string; corresponds to
    the HTML "<textarea>" tag.

    Instance attributes:
      value : string
    """

    def _parse(self, request: HTTPRequest) -> None:
        Widget._parse(self, request)
        if isinstance(self.value, str) and self.value.find("\r\n") >= 0:
            self.value = self.value.replace("\r\n", "\n")

    def render_content(self) -> Rendered:
        return (
            htmltag("textarea", name=self.name, **self.attrs)
            + htmlescape(self.value or "")
            + htmltext("</textarea>")
        )


class CheckboxWidget(Widget):
    """Widget for a single checkbox: corresponds to "<input
    type=checkbox>".  Do not put multiple CheckboxWidgets with the same
    name in the same form.

    Instance attributes:
      value : boolean
    """

    def _parse(self, request: HTTPRequest) -> None:
        self.value = self.name in request.form

    def render_content(self) -> Rendered:
        return htmltag(
            "input",
            xml_end=True,
            type="checkbox",
            name=self.name,
            value="yes",
            checked=self.value and "checked" or None,
            **self.attrs,
        )


class SelectWidget(Widget):
    """Widget for single or multiple selection; corresponds to
    <select name=...>
      <option value="Foo">Foo</option>
      ...
    </select>

    Instance attributes:
      options : [ (value:any, description:any, key:string) ]
      value : any
        The value is None or an element of dict(options.values()).
    """

    SELECTION_ERROR = "invalid value selected"

    options: list[Option]
    verify_selection: bool

    def __init__(
        self,
        name: str,
        value: object | None = None,
        options: Sequence[Any] | None = None,
        sort: bool = False,
        verify_selection: bool = True,
        **kwargs: Any,
    ) -> None:
        assert self.__class__ is not SelectWidget, "abstract class"
        Widget.__init__(self, name, value, **kwargs)
        self.options = []
        if not options:
            # The HTML and XHTML specifications require select elements to
            # contain at least one option.
            raise ValueError("a non-empty list of 'options' is required")
        else:
            self.set_options(options, sort)
        self.verify_selection = verify_selection

    def get_allowed_values(self) -> list[object]:
        return [item[0] for item in self.options]

    def get_descriptions(self) -> list[object]:
        return [item[1] for item in self.options]

    def set_value(self, value: object | None) -> None:
        self.value = None
        for object, _description, _key in self.options:
            if value == object:
                self.value = value
                break

    def _generate_keys(
        self,
        values: Sequence[object],
        descriptions: Sequence[object],
    ) -> list[str]:
        """Called if no keys were provided.  Try to generate a set of keys
        that will be consistent between rendering and parsing.
        """
        # try to use ZODB object IDs
        keys: list[str] = []
        for value in values:
            if value is None:
                oid = ""
            else:
                oid = getattr(value, "_p_oid", None)
                if not oid:
                    break
                hi, lo = struct.unpack(">LL", oid)
                oid = "%x" % ((hi << 32) | lo)
            keys.append(oid)
        else:
            # found OID for every value
            return keys
        # can't use OIDs, try using descriptions
        used_keys: dict[str, int] = {}
        keys = list(map(stringify, descriptions))
        for key in keys:
            if key in used_keys:
                raise ValueError("duplicated descriptions (provide keys)")
            used_keys[key] = 1
        return keys

    def set_options(
        self,
        options: Sequence[Any],
        sort: bool = False,
    ) -> None:
        """(options: [objects:any], sort=False)
        or
          (options: [(object:any, description:any)], sort=False)
        or
          (options: [(object:any, description:any, key:any)], sort=False)
        """

        """
        Set the options list.  The list of options can be a list of
        objects, in which case the descriptions default to map(htmlescape,
        objects) applying htmlescape() to each description and key.
        If keys are provided they must be distinct.  If the sort
        keyword argument is true, sort the options by case-insensitive
        lexicographic order of descriptions, except that options with
        value None appear before others.
        """
        normalized_options: list[Option] = []
        if options:
            first = options[0]
            values: list[object] = []
            descriptions: list[object] = []
            keys: list[str] = []
            if isinstance(first, tuple):
                if len(first) == 2:
                    for value, description in options:
                        values.append(value)
                        descriptions.append(description)
                elif len(first) == 3:
                    for value, description, key in options:
                        values.append(value)
                        descriptions.append(description)
                        keys.append(stringify(key))
                else:
                    raise ValueError('invalid options %r' % options)
            else:
                values = descriptions = list(options)

            if not keys:
                keys = self._generate_keys(values, descriptions)

            normalized_options = list(zip(values, descriptions, keys))

            if sort:

                def make_sort_key(option: Option) -> str:
                    value, description, key = option
                    if value is None:
                        return ''
                    else:
                        return stringify(description).lower()

                normalized_options.sort(key=make_sort_key)
        self.options = normalized_options

    def _parse_single_selection(
        self,
        parsed_key: object,
        default: object | None = None,
    ) -> object | None:
        for value, _description, key in self.options:
            if key == parsed_key:
                return value
        else:
            if self.verify_selection:
                self.error = self.SELECTION_ERROR
                return default
            elif self.options:
                return self.options[0][0]
            else:
                return default

    def set_allowed_values(
        self,
        allowed_values: Sequence[object],
        descriptions: Sequence[object] | None = None,
        sort: bool = False,
    ) -> None:
        """(allowed_values:[any], descriptions:[any], sort:boolean=False)

        Set the options for this widget.  The allowed_values and descriptions
        parameters must be sequences of the same length.  The sort option
        causes the options to be sorted using case-insensitive lexicographic
        order of descriptions, except that options with value None appear
        before others.
        """
        if descriptions is None:
            self.set_options(allowed_values, sort)
        else:
            assert len(descriptions) == len(allowed_values)
            self.set_options(list(zip(allowed_values, descriptions)), sort)

    def is_selected(self, value: object) -> bool:
        return value == self.value

    def render_content(self) -> Rendered:
        tags = [htmltag("select", name=self.name, **self.attrs)]
        for object, description, key in self.options:
            if self.is_selected(object):
                selected = 'selected'
            else:
                selected = None
            if description is None:
                description = ""
            r = htmltag("option", value=key, selected=selected)
            tags.append(r + htmlescape(description) + htmltext('</option>'))
        tags.append(htmltext("</select>"))
        return htmltext("\n").join(tags)


class SingleSelectWidget(SelectWidget):
    """Dropdown for one choice (``<select>``); value is the chosen option."""

    SELECT_TYPE = "single_select"
    MULTIPLE_SELECTION_ERROR = "cannot select multiple values"

    def _parse(self, request: HTTPRequest) -> None:
        parsed_key = request.form.get(self.name)
        if parsed_key:
            if isinstance(parsed_key, list):
                self.error = self.MULTIPLE_SELECTION_ERROR
            else:
                self.value = self._parse_single_selection(parsed_key)
        else:
            self.value = None


class RadiobuttonsWidget(SingleSelectWidget):
    """Widget for a *set* of related radiobuttons -- all have the
    same name, but different values (and only one of those values
    is returned by the whole group).

    Instance attributes:
      delim : string = None
        string to emit between each radiobutton in the group.  If
        None, a single newline is emitted.
    """

    SELECT_TYPE = "radiobuttons"
    delim: str

    def __init__(
        self,
        name: str,
        value: object | None = None,
        options: Sequence[Any] | None = None,
        delim: str | None = None,
        **kwargs: Any,
    ) -> None:
        SingleSelectWidget.__init__(
            self, name, value, options=options, **kwargs
        )
        if delim is None:
            self.delim = "\n"
        else:
            self.delim = delim
        self.attrs = merge_attrs(self.attrs, {'id': None})

    def render_content(self) -> Rendered:
        tags: list[htmltext] = []
        for object, description, key in self.options:
            if self.is_selected(object):
                checked = 'checked'
            else:
                checked = None
            r = htmltag(
                "input",
                xml_end=True,
                type="radio",
                name=self.name,
                value=key,
                checked=checked,
                **self.attrs,
            )
            tags.append(r + htmlescape(description))
        return htmlescape(self.delim).join(tags)


class MultipleSelectWidget(SelectWidget):
    """Widget for multiple selection.

    Instance attributes:
      value : [any]
        for multipe selects, the value is None or a list of
        elements from dict(self.options).values()
    """

    SELECT_TYPE = "multiple_select"

    def __init__(
        self,
        name: str,
        value: object | None = None,
        options: Sequence[Any] | None = None,
        **kwargs: Any,
    ) -> None:
        SelectWidget.__init__(
            self, name, value, options=options, multiple='multiple', **kwargs
        )

    def set_value(self, value: object | None) -> None:
        allowed_values = self.get_allowed_values()
        if value in allowed_values:
            self.value = [value]
        elif isinstance(value, (list, tuple)):
            self.value = [
                element for element in value if element in allowed_values
            ] or None
        else:
            self.value = None

    def is_selected(self, value: object) -> bool:
        if self.value is None:
            return value is None
        elif isinstance(self.value, list):
            return value in self.value
        else:
            return False

    def _parse(self, request: HTTPRequest) -> None:
        parsed_keys = request.form.get(self.name)
        if parsed_keys:
            if isinstance(parsed_keys, list):
                self.value = [
                    value
                    for value, description, key in self.options
                    if key in parsed_keys
                ] or None
            else:
                _marker = []
                value = self._parse_single_selection(parsed_keys, _marker)
                if value is _marker:
                    self.value = None
                else:
                    self.value = [value]
        else:
            self.value = None


class ButtonWidget(Widget):
    """Base class for button controls (``<input type="button">``).

    The constructor's `value` argument is the button label.  After parsing,
    the widget's `value` is a boolean: true when this button's name appears in
    the submission, i.e. when this button was clicked.

    Instance attributes:
      label : any
        the text shown on the button.
      value : bool
        true if the button was clicked.
    """

    HTML_TYPE = "button"
    label: object

    def __init__(
        self,
        name: str,
        value: object | None = None,
        **kwargs: Any,
    ) -> None:
        Widget.__init__(self, name, value=None, **kwargs)
        self.set_label(value)

    def set_label(self, label: object) -> None:
        self.label = label

    def get_label(self) -> object:
        return self.label

    def render_content(self) -> Rendered:
        # slightly different behavior here, we always render the
        # tag using the 'value' passed in as a parameter.  'self.value'
        # is a boolean that is true if the button's name appears
        # in the request.
        value = self.label and htmlescape(self.label) or None
        return htmltag(
            "input",
            xml_end=True,
            type=self.HTML_TYPE,
            name=self.name,
            value=value,
            **self.attrs,
        )

    def _parse(self, request: HTTPRequest) -> None:
        self.value = self.name in request.form


class SubmitWidget(ButtonWidget):
    """Submit button (``<input type="submit">``).

    Its parsed value is true when this button submitted the form; `Form` uses
    the submit widgets to answer `Form.get_submit`.
    """

    HTML_TYPE = "submit"


class ResetWidget(ButtonWidget):
    """Reset button (``<input type="reset">``) clearing the form."""

    HTML_TYPE = "reset"


class HiddenWidget(Widget):
    """Hidden field (``<input type="hidden">``) carrying a string value.

    Renders with no title, hint, or error decoration and cannot hold an
    error.  Used to pass state through a form round-trip.

    Instance attributes:
      value : string
    """

    def set_error(self, error: str | None) -> None:
        """Hidden widgets cannot hold an error (raises TypeError)."""
        if error is not None:
            raise TypeError('error not allowed on hidden widgets')

    def render_content(self) -> Rendered:
        if self.value is None:
            value = None
        else:
            value = htmlescape(self.value)
        return htmltag(
            "input",
            xml_end=True,
            type="hidden",
            name=self.name,
            value=value,
            **self.attrs,
        )

    def render(self) -> Rendered:
        return (
            self.render_content()
        )  # Input elements of type hidden have no decoration.


# -- Derived widget types ----------------------------------------------
# (these don't correspond to fundamental widget types in HTML,
# so they're separated)


class NumberWidget(StringWidget):
    """Abstract text input that parses to a number.

    Subclasses set `TYPE_OBJECT` (``int`` or ``float``) and `TYPE_ERROR` (the
    message shown for non-numeric input).  See `IntWidget` and `FloatWidget`.
    """

    # Parameterize the number type (either float or int) through
    # these class attributes:
    TYPE_OBJECT: type[int] | type[float] | None = None  # eg. int, float
    TYPE_ERROR: str | None = None  # human-readable error message

    def __init__(
        self,
        name: str,
        value: int | float | None = None,
        **kwargs: Any,
    ) -> None:
        assert self.__class__ is not NumberWidget, "abstract class"
        assert value is None or type(value) is self.TYPE_OBJECT, (
            "form value '%s' not a %s: got %r"
            % (
                name,
                self.TYPE_OBJECT,
                value,
            )
        )
        StringWidget.__init__(self, name, value, **kwargs)

    def _parse(self, request: HTTPRequest) -> None:
        StringWidget._parse(self, request)
        type_object = self.TYPE_OBJECT
        if self.value is not None and type_object is not None:
            try:
                self.value = type_object(stringify(self.value))
            except ValueError:
                self.error = self.TYPE_ERROR


class FloatWidget(NumberWidget):
    """Text input whose value parses to a ``float`` (error if not numeric).

    Instance attributes:
      value : float
    """

    TYPE_OBJECT = float
    TYPE_ERROR = "must be a number"


class IntWidget(NumberWidget):
    """Text input whose value parses to an ``int`` (error if not an integer).

    Instance attributes:
      value : int
    """

    TYPE_OBJECT = int
    TYPE_ERROR = "must be an integer"


class OptionSelectWidget(SingleSelectWidget):
    """Widget for single selection with automatic submission. Parse
    will always return a value from it's options, even if the form is
    not submitted. This allows its value to be used to decide what
    other widgets need to be created in a form.  It's a powerful
    feature but it can be hard to understand what's going on.

    Instance attributes:
      value : any
    """

    SELECT_TYPE = "option_select"

    def __init__(
        self,
        name: str,
        value: object | None = None,
        options: Sequence[Any] | None = None,
        **kwargs: Any,
    ) -> None:
        SingleSelectWidget.__init__(
            self, name, value, options=options, onchange='submit()', **kwargs
        )

    def parse(self, request: HTTPRequest | None = None) -> object | None:
        if not self._parsed:
            if request is None:
                request = current_request()
            self._parse(request)
            self._parsed = True
        return self.value

    def _parse(self, request: HTTPRequest) -> None:
        parsed_key = request.form.get(self.name)
        if parsed_key:
            if isinstance(parsed_key, list):
                self.error = self.MULTIPLE_SELECTION_ERROR
            else:
                self.value = self._parse_single_selection(parsed_key)
        elif self.value is None:
            self.value = self.options[0][0]

    def render_content(self) -> Rendered:
        return SingleSelectWidget.render_content(self) + htmltext(
            '<noscript><input type="submit" value="apply" /></noscript>'
        )


class CompositeWidget(Widget):
    """A widget built from named sub-widgets, parsed and rendered together.

    Add children with `add` (as with `Form`); each child's HTML name is
    prefixed so it stays unique.  Parsing parses all children, and
    `has_error` is true if the composite or any child has an error.  Reach
    children with ``widget[name]`` / `get` for values or `get_widget` for the
    widget objects.  `WidgetList` and `WidgetDict` are variable-length
    subclasses.

    Instance attributes:
      widgets : [Widget]
        the child widgets, in render order.
    """

    widgets: list[Widget]
    _names: dict[str, Widget]

    def __init__(
        self,
        name: str,
        value: object | None = None,
        **kwargs: Any,
    ) -> None:
        Widget.__init__(self, name, value, **kwargs)
        self.widgets = []
        self._names = {}

    def _parse(self, request: HTTPRequest) -> None:
        for widget in self.widgets:
            widget.parse(request)

    def __getitem__(self, name: str) -> object | None:
        return self._names[name].parse()

    def get(self, name: str) -> object | None:
        """Return the parsed value of the named child widget, or None."""
        widget = self._names.get(name)
        if widget:
            return widget.parse()
        return None

    def get_widget(self, name: str) -> Widget | None:
        """Return the named child widget, or None if it does not exist."""
        return self._names.get(name)

    def get_widgets(self) -> list[Widget]:
        """Return the child widgets in render order."""
        return self.widgets

    def clear_error(self, request: HTTPRequest | None = None) -> None:
        Widget.clear_error(self, request)
        for widget in self.widgets:
            widget.clear_error(request)

    def set_widget_error(self, name: str, error: str | None) -> None:
        self._names[name].set_error(error)

    def has_error(self, request: HTTPRequest | None = None) -> bool:
        has_error = False
        if Widget.has_error(self, request=request):
            has_error = True
        for widget in self.widgets:
            if widget.has_error(request=request):
                has_error = True
        return has_error

    def add(
        self,
        widget_class: type[Widget],
        name: str,
        *args: Any,
        **kwargs: Any,
    ) -> None:
        """Add a child widget under `name` (name is prefixed to stay unique).

        Same calling convention as `Form.add`.  Raises ValueError if `name` is
        already used within this composite.
        """
        if name in self._names:
            raise ValueError('the name %r is already used' % name)
        if self.attrs.get('disabled') and 'disabled' not in kwargs:
            kwargs['disabled'] = True
        widget = widget_class(subname(self.name, name), *args, **kwargs)
        self._names[name] = widget
        self.widgets.append(widget)

    def render_content(self) -> Rendered:
        r = TemplateIO(html=True)
        for widget in self.get_widgets():
            r += widget.render()
        return r.getvalue()


class WidgetList(CompositeWidget):
    """A variable length list of widgets.  There is only one
    title and hint but each element of the list can have its own
    error.  You can also set an error on the WidgetList itself (e.g. as a
    result of higher-level processing).

    Instance attributes:
      element_names : [string]
    """

    element_names: list[str]

    def __init__(
        self,
        name: str,
        value: list[object] | None = None,
        element_type: type[Widget] = StringWidget,
        element_kwargs: dict[str, object] | None = None,
        add_element_label: str | htmltext = "Add row",
        **kwargs: Any,
    ) -> None:
        element_kwargs = element_kwargs or {}
        assert value is None or type(value) is list, (
            "value '%s' not a list: got %r" % (name, value)
        )
        assert issubclass(element_type, Widget), (
            "value '%s' element_type not a Widget: "
            "got %r"
            % (
                name,
                element_type,
            )
        )
        assert type(element_kwargs) is dict, (
            "value '%s' element_kwargs not a dict: "
            "got %r"
            % (
                name,
                element_kwargs,
            )
        )
        assert isinstance(add_element_label, (str, htmltext)), (
            "value '%s'add_element_label not a string: "
            "got %r"
            % (
                name,
                add_element_label,
            )
        )

        CompositeWidget.__init__(self, name, value, **kwargs)
        self.element_names = []

        self.add(HiddenWidget, 'added_elements')
        added_elements_widget = self.get_widget('added_elements')
        assert added_elements_widget is not None

        def add_element(value: object | None = None) -> None:
            name = "element%d" % len(self.element_names)
            self.add(element_type, name, value=value, **element_kwargs)
            self.element_names.append(name)

        # Add element widgets for initial value
        if value is not None:
            for element_value in value:
                add_element(value=element_value)

        # Add at least one additional element widget
        num_added = int(stringify(added_elements_widget.parse() or 1))
        for _i in range(num_added):
            add_element()

        # Add submit to add more element widgets
        self.add(SubmitWidget, 'add_element', value=add_element_label)
        if self.get('add_element'):
            add_element()
            num_added += 1
        added_elements_widget.set_value(num_added)

    def _parse(self, request: HTTPRequest) -> None:
        values: list[object] = []
        for name in self.element_names:
            value = self.get(name)
            if value is not None:
                values.append(value)
        self.value = values or None

    def render_content(self) -> Rendered:
        r = TemplateIO(html=True)
        add_element_widget = self.get_widget('add_element')
        assert add_element_widget is not None
        for widget in self.get_widgets():
            if widget is add_element_widget:
                continue
            r += widget.render()
        r += add_element_widget.render()
        return r.getvalue()

    def render(self) -> Rendered:
        r = TemplateIO(html=True)
        r += self.render_title(self.get_title())
        add_element_widget = self.get_widget('add_element')
        assert add_element_widget is not None
        for widget in self.get_widgets():
            if widget is add_element_widget:
                continue
            r += widget.render()
        r += add_element_widget.render()
        r += self.render_hint(self.get_hint())
        return r.getvalue()


class WidgetDict(CompositeWidget):
    """A variable length dict of widgets.  There is only one
    title and hint but each element of the dict can have its own
    error.  You can also set an error on the WidgetDict itself (e.g. as a
    result of higher-level processing).

    Instance attributes:
      element_names : [string]
    """

    element_names: list[str]

    def __init__(
        self,
        name: str,
        value: dict[object, object] | None = None,
        element_key_type: type[Widget] = StringWidget,
        element_value_type: type[Widget] = StringWidget,
        element_key_kwargs: dict[str, object] = {},  # noqa: B006
        element_value_kwargs: dict[str, object] = {},  # noqa: B006
        add_element_label: str | htmltext = 'Add row',
        **kwargs: Any,
    ) -> None:
        assert value is None or type(value) is dict, (
            'value %r not a dict: got %r' % (name, value)
        )
        assert issubclass(element_key_type, Widget), (
            "value '%s' element_key_type not a Widget: "
            "got %r"
            % (
                name,
                element_key_type,
            )
        )
        assert issubclass(element_value_type, Widget), (
            "value '%s' element_value_type not a Widget: "
            "got %r"
            % (
                name,
                element_value_type,
            )
        )
        assert type(element_key_kwargs) is dict, (
            "value '%s' element_key_kwargs not a dict: "
            "got %r"
            % (
                name,
                element_key_kwargs,
            )
        )
        assert type(element_value_kwargs) is dict, (
            "value '%s' element_value_kwargs not a dict: "
            "got %r"
            % (
                name,
                element_value_kwargs,
            )
        )
        assert isinstance(add_element_label, (str, htmltext)), (
            'value %r element_name not a string: '
            'got %r'
            % (
                name,
                add_element_label,
            )
        )

        CompositeWidget.__init__(self, name, value, **kwargs)
        self.element_names = []

        self.add(HiddenWidget, 'added_elements')
        added_elements_widget = self.get_widget('added_elements')
        assert added_elements_widget is not None

        def add_element(
            key: object | None = None,
            value: object | None = None,
        ) -> None:
            name = 'element%d' % len(self.element_names)
            self.add(
                element_key_type,
                name + 'key',
                value=key,
                render_br=False,
                **element_key_kwargs,
            )
            self.add(
                element_value_type,
                name + 'value',
                value=value,
                **element_value_kwargs,
            )
            self.element_names.append(name)

        # Add element widgets for initial value
        if value is not None:
            for key, element_value in value.items():
                add_element(key=key, value=element_value)

        # Add at least one additional element widget
        num_added = int(stringify(added_elements_widget.parse() or 1))
        for _i in range(num_added):
            add_element()

        # Add submit to add more element widgets
        self.add(SubmitWidget, 'add_element', value=add_element_label)
        if self.get('add_element'):
            add_element()
            num_added += 1
        added_elements_widget.set_value(num_added)

    def _parse(self, request: HTTPRequest) -> None:
        values: dict[object, object] = {}
        for name in self.element_names:
            key = self.get(name + 'key')
            value = self.get(name + 'value')
            if key and value:
                values[key] = value
        self.value = values or None

    def render_content(self) -> Rendered:
        r = TemplateIO(html=True)
        for name in self.element_names:
            if name in ('add_element', 'added_elements'):
                continue
            key_widget = self.get_widget(name + 'key')
            value_widget = self.get_widget(name + 'value')
            assert key_widget is not None
            assert value_widget is not None
            r += htmltext('%s<div class="widget">: </div>%s') % (
                key_widget.render(),
                value_widget.render(),
            )
            if self.render_br:
                r += htmltext('<br clear="left" class="widget" />')
            r += htmltext('\n')
        add_element_widget = self.get_widget('add_element')
        added_elements_widget = self.get_widget('added_elements')
        assert add_element_widget is not None
        assert added_elements_widget is not None
        r += add_element_widget.render()
        r += added_elements_widget.render()
        return r.getvalue()
