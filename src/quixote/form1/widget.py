"""Provides the basic web widget classes: Widget itself, plus StringWidget,
TextWidget, CheckboxWidget, etc.
"""

from __future__ import annotations

import struct
from collections.abc import Callable, MutableMapping, Sequence
from typing import TYPE_CHECKING, Any, ClassVar, cast

from quixote import get_request
from quixote.html import htmlescape, htmltag, htmltext
from quixote.http_request import FieldValue, Upload

if TYPE_CHECKING:
    from quixote.http_request import HTTPRequest

FloatType = float
IntType = int
ListType = list
StringType = str
TupleType = tuple

type Rendered = str | htmltext
type Option = tuple[object, object, str]


class FormValueError(Exception):
    """Raised whenever a widget has problems parsing its value."""

    msg: object

    def __init__(self, msg: object) -> None:
        self.msg = msg

    def __str__(self) -> str:
        return str(self.msg)


class Widget:
    """Abstract base class for web widgets.  The key elements
    of a web widget are:
      - name
      - widget type (how the widget looks/works in the browser)
      - value

    The name and value are instance attributes (because they're specific to
    a particular widget in a particular context); widget type is a
    class attributes.

    Instance attributes:
      name : string
      value : any

    Feel free to access these directly; to set them, use the 'set_*()'
    modifier methods.
    """

    # Subclasses must define.  'widget_type' is just a string, e.g.
    # "string", "text", "checkbox".
    widget_type: ClassVar[str | None] = None

    name: Any
    value: object | None

    def __init__(self, name: Any, value: object | None = None) -> None:
        assert self.__class__ is not Widget, "abstract class"
        self.set_name(name)
        self.set_value(value)

    def __repr__(self) -> str:
        return "<%s at %x: %s>" % (
            self.__class__.__name__,
            id(self),
            self.name,
        )

    def __str__(self) -> str:
        return "%s: %s" % (self.widget_type, self.name)

    def set_name(self, name: Any) -> None:
        self.name = name

    def set_value(self, value: object | None) -> None:
        self.value = value

    def clear(self) -> None:
        self.value = None

    # -- Subclasses must implement these -------------------------------

    def render(self, request: HTTPRequest) -> Rendered:
        """render(request) -> HTML text"""
        raise NotImplementedError

    def parse(self, request: HTTPRequest) -> object | None:
        """parse(request) -> any"""
        value = request.form.get(self.name)
        if type(value) is StringType and value.strip():
            self.value = value
        else:
            self.value = None

        return self.value

    # -- Convenience methods for subclasses ----------------------------

    # This one's really only for composite widgets; lives here until
    # we have a demonstrated need for a CompositeWidget class.
    def get_subwidget_name(self, name: str) -> str:
        return "%s$%s" % (self.name, name)

    def create_subwidget(
        self,
        widget_type: str | type[Widget],
        widget_name: str,
        value: object | None = None,
        **args: Any,
    ) -> Widget:
        from quixote.form1 import form

        klass = form.get_widget_class(widget_type)
        name = self.get_subwidget_name(widget_name)
        return cast(type[Widget], klass)(*(name, value), **args)


# class Widget

# -- Fundamental widget types ------------------------------------------
# These correspond to the standard types of input tag in HTML:
#   text     StringWidget
#   password PasswordWidget
#   radio    RadiobuttonWidget
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
      size : int
      maxlength : int
    """

    widget_type = "string"

    # This lets PasswordWidget be a trivial subclass
    html_type = "text"

    size: int | None
    maxlength: int | None

    def __init__(
        self,
        name: str,
        value: object | None = None,
        size: int | None = None,
        maxlength: int | None = None,
    ) -> None:
        Widget.__init__(self, name, value)
        self.size = size
        self.maxlength = maxlength

    def render(self, request: HTTPRequest, **attributes: Any) -> Rendered:
        return htmltag(
            "input",
            xml_end=1,
            type=self.html_type,
            name=self.name,
            size=self.size,
            maxlength=self.maxlength,
            value=self.value,
            **attributes,
        )


class FileWidget(StringWidget):
    """Trivial subclass of StringWidget for uploading files.

    Instance attributes: none
    """

    widget_type = "file"
    html_type = "file"

    def parse(self, request: HTTPRequest) -> object | None:
        """parse(request) -> any"""
        value = request.form.get(self.name)
        if isinstance(value, Upload):
            self.value = value
        else:
            self.value = None
        return self.value


class PasswordWidget(StringWidget):
    """Trivial subclass of StringWidget for entering passwords (different
    widget type because HTML does it that way).

    Instance attributes: none
    """

    widget_type = "password"
    html_type = "password"


class TextWidget(Widget):
    """Widget for entering a long, multi-line string; corresponds to
    the HTML "<textarea>" tag.

    Instance attributes:
      value : string
      cols : int
      rows : int
      wrap : string
        (see an HTML book for details on text widget wrap options)
      css_class : string
    """

    widget_type = "text"

    cols: int | None
    rows: int | None
    wrap: str | None
    css_class: str | None

    def __init__(
        self,
        name: str,
        value: object | None = None,
        cols: int | None = None,
        rows: int | None = None,
        wrap: str | None = None,
        css_class: str | None = None,
    ) -> None:
        Widget.__init__(self, name, value)
        self.cols = cols
        self.rows = rows
        self.wrap = wrap
        self.css_class = css_class

    def render(self, request: HTTPRequest) -> Rendered:
        return (
            htmltag(
                "textarea",
                name=self.name,
                cols=self.cols,
                rows=self.rows,
                wrap=self.wrap,
                css_class=self.css_class,
            )
            + htmlescape(self.value or "")
            + htmltext("</textarea>")
        )

    def parse(self, request: HTTPRequest) -> object | None:
        value = Widget.parse(self, request)
        if isinstance(value, str):
            value = value.replace("\r\n", "\n")
            self.value = value
        return self.value


class CheckboxWidget(Widget):
    """Widget for a single checkbox: corresponds to "<input
    type=checkbox>".  Do not put multiple CheckboxWidgets with the same
    name in the same form.

    Instance attributes:
      value : boolean
    """

    widget_type = "checkbox"

    def render(self, request: HTTPRequest) -> Rendered:
        return htmltag(
            "input",
            xml_end=1,
            type="checkbox",
            name=self.name,
            value="yes",
            checked=self.value and "checked" or None,
        )

    def parse(self, request: HTTPRequest) -> bool:
        self.value = self.name in request.form
        return self.value


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
      size : int
        The number of options that should be presented without scrolling.
    """

    # NB. 'widget_type' not set here because this is an abstract class: it's
    # set by subclasses SingleSelectWidget and MultipleSelectWidget.

    options: list[Option]
    size: int | None
    verify_selection: bool | int

    def __init__(
        self,
        name: str,
        value: object | None = None,
        allowed_values: Sequence[object] | None = None,
        descriptions: Sequence[object] | None = None,
        options: Sequence[Any] | None = None,
        size: int | None = None,
        sort: bool | int = 0,
        verify_selection: bool | int = 1,
    ) -> None:
        assert self.__class__ is not SelectWidget, "abstract class"
        self.options = []
        # if options passed, cannot pass allowed_values or descriptions
        if allowed_values is not None:
            assert options is None, (
                'cannot pass both allowed_values and options'
            )
            assert allowed_values, 'cannot pass empty allowed_values list'
            self.set_allowed_values(allowed_values, descriptions, sort)
        elif options is not None:
            assert descriptions is None, (
                'cannot pass both options and descriptions'
            )
            assert options, 'cannot pass empty options list'
            self.set_options(options, sort)
        self.set_name(name)
        self.set_value(value)
        self.size = size
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
        keys = list(map(str, descriptions))
        for key in keys:
            if key in used_keys:
                raise ValueError("duplicated descriptions (provide keys)")
            used_keys[key] = 1
        return keys

    def set_options(
        self,
        options: Sequence[Any],
        sort: bool | int = 0,
    ) -> None:
        """(options: [objects:any], sort=0)
        or
          (options: [(object:any, description:any)], sort=0)
        or
          (options: [(object:any, description:any, key:any)], sort=0)
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
            if type(first) is TupleType:
                if len(first) == 2:
                    for value, description in options:
                        values.append(value)
                        descriptions.append(description)
                elif len(first) == 3:
                    for value, description, key in options:
                        values.append(value)
                        descriptions.append(description)
                        keys.append(str(key))
                else:
                    raise ValueError('invalid options %r' % options)
            else:
                values = descriptions = list(options)

            if not keys:
                keys = self._generate_keys(values, descriptions)

            normalized_options = list(zip(values, descriptions, keys))

            if sort:

                def make_sort_key(option: Option) -> tuple[str, Option]:
                    value, description, key = option
                    if value is None:
                        return ('', option)
                    else:
                        return (str(description).lower(), option)

                doptions = sorted(map(make_sort_key, normalized_options))
                normalized_options = [item[1] for item in doptions]
        self.options = normalized_options

    def parse_single_selection(self, parsed_key: object) -> object:
        for value, _description, key in self.options:
            if key == parsed_key:
                return value
        else:
            if self.verify_selection:
                raise FormValueError("invalid value selected")
            else:
                return self.options[0][0]

    def set_allowed_values(
        self,
        allowed_values: Sequence[object],
        descriptions: Sequence[object] | None = None,
        sort: bool | int = 0,
    ) -> None:
        """(allowed_values:[any], descriptions:[any], sort:boolean=0)

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

    def render(self, request: HTTPRequest) -> Rendered:
        if self.widget_type == "multiple_select":
            multiple = "multiple"
        else:
            multiple = None
        if self.widget_type == "option_select":
            onchange = "submit()"
        else:
            onchange = None
        tags = [
            htmltag(
                "select",
                name=self.name,
                multiple=multiple,
                onchange=onchange,
                size=self.size,
            )
        ]
        for object, description, key in self.options:
            if self.is_selected(object):
                selected = "selected"
            else:
                selected = None
            if description is None:
                description = ""
            r = htmltag("option", value=key, selected=selected)
            tags.append(r + htmlescape(description) + htmltext('</option>'))
        tags.append(htmltext("</select>"))
        return htmltext("\n").join(tags)


class SingleSelectWidget(SelectWidget):
    """Widget for single selection."""

    widget_type = "single_select"

    def parse(self, request: HTTPRequest) -> object | None:
        parsed_key = request.form.get(self.name)
        self.value = None
        if parsed_key:
            if type(parsed_key) is ListType:
                raise FormValueError("cannot select multiple values")
            self.value = self.parse_single_selection(parsed_key)
        return self.value


class RadiobuttonsWidget(SingleSelectWidget):
    """Widget for a *set* of related radiobuttons -- all have the
    same name, but different values (and only one of those values
    is returned by the whole group).

    Instance attributes:
      delim : string = None
        string to emit between each radiobutton in the group.  If
        None, a single newline is emitted.
    """

    widget_type = "radiobuttons"
    delim: str

    def __init__(
        self,
        name: str,
        value: object | None = None,
        allowed_values: Sequence[object] | None = None,
        descriptions: Sequence[object] | None = None,
        options: Sequence[Any] | None = None,
        delim: str | None = None,
    ) -> None:
        SingleSelectWidget.__init__(
            self, name, value, allowed_values, descriptions, options
        )
        if delim is None:
            self.delim = "\n"
        else:
            self.delim = delim

    def render(self, request: HTTPRequest) -> Rendered:
        tags: list[htmltext] = []
        for object, description, key in self.options:
            if self.is_selected(object):
                checked = "checked"
            else:
                checked = None
            r = htmltag(
                "input",
                xml_end=True,
                type="radio",
                name=self.name,
                value=key,
                checked=checked,
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

    widget_type = "multiple_select"

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

    def parse(self, request: HTTPRequest) -> object | None:
        parsed_keys = request.form.get(self.name)
        self.value = None
        if parsed_keys:
            if type(parsed_keys) is ListType:
                self.value = [
                    value
                    for value, description, key in self.options
                    if key in parsed_keys
                ] or None
            else:
                self.value = [self.parse_single_selection(parsed_keys)]
        return self.value


class SubmitButtonWidget(Widget):
    """
    Instance attributes:
      value : boolean
    """

    widget_type = "submit_button"

    def __init__(
        self,
        name: str | None = None,
        value: object | None = None,
    ) -> None:
        Widget.__init__(self, name, value)

    def render(self, request: HTTPRequest) -> Rendered:
        value = self.value and htmlescape(self.value) or None
        return htmltag(
            "input", xml_end=1, type="submit", name=self.name, value=value
        )

    def parse(self, request: HTTPRequest) -> object | None:
        return request.form.get(self.name)

    def is_submitted(self) -> object | None:
        return self.parse(get_request())


class HiddenWidget(Widget):
    """
    Instance attributes:
      value : string
    """

    widget_type = "hidden"

    def render(self, request: HTTPRequest) -> Rendered:
        if self.value is None:
            value = None
        else:
            value = htmlescape(self.value)
        return htmltag(
            "input", xml_end=1, type="hidden", name=self.name, value=value
        )

    def set_current_value(self, value: object | None) -> None:
        self.value = value
        request = get_request()
        if request.form:
            form = cast(MutableMapping[str, FieldValue], request.form)
            form[str(self.name)] = cast(FieldValue, value)

    def get_current_value(self) -> object | None:
        request = get_request()
        if request.form:
            return self.parse(request)
        else:
            return self.value


# -- Derived widget types ----------------------------------------------
# (these don't correspond to fundamental widget types in HTML,
# so they're separated)


class NumberWidget(StringWidget):
    """
    Instance attributes: none
    """

    # Parameterize the number type (either float or int) through
    # these class attributes:
    type_object: ClassVar[type[int] | type[float] | None] = None
    type_error: ClassVar[str | None] = None
    type_converter: ClassVar[Callable[[Any], int | float] | None] = None

    def __init__(
        self,
        name: str,
        value: int | float | None = None,
        size: int | None = None,
        maxlength: int | None = None,
    ) -> None:
        assert self.__class__ is not NumberWidget, "abstract class"
        assert value is None or type(value) is self.type_object, (
            "form value '%s' not a %s: got %r"
            % (
                name,
                self.type_object,
                value,
            )
        )
        StringWidget.__init__(self, name, value, size, maxlength)

    def parse(self, request: HTTPRequest) -> int | float | None:
        value = StringWidget.parse(self, request)
        if value:
            converter = self.type_converter
            assert converter is not None
            try:
                self.value = converter(value)
            except ValueError:
                raise FormValueError(self.type_error)
        return cast(int | float | None, self.value)


class FloatWidget(NumberWidget):
    """
    Instance attributes:
      value : float
    """

    widget_type = "float"
    type_object = FloatType
    type_converter = float
    type_error = "must be a number"


class IntWidget(NumberWidget):
    """
    Instance attributes:
      value : int
    """

    widget_type = "int"
    type_object = IntType
    type_converter = int
    type_error = "must be an integer"


class OptionSelectWidget(SingleSelectWidget):
    """Widget for single selection with automatic submission and early
    parsing.  This widget parses the request when it is created.  This
    allows its value to be used to decide what other widgets need to be
    created in a form.  It's a powerful feature but it can be hard to
    understand what's going on.

    Instance attributes:
      value : any
    """

    widget_type = "option_select"

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        SingleSelectWidget.__init__(self, *args, **kwargs)

        request = get_request()
        if request.form:
            SingleSelectWidget.parse(self, request)
        if self.value is None:
            self.value = self.options[0][0]

    def render(self, request: HTTPRequest) -> Rendered:
        return SingleSelectWidget.render(self, request) + htmltext(
            '<noscript>'
            '<input type="submit" name="" value="apply" />'
            '</noscript>'
        )

    def parse(self, request: HTTPRequest) -> object | None:
        return self.value

    def get_current_option(self) -> object | None:
        return self.value


class ListWidget(Widget):
    """Widget for lists of objects.

    Instance attributes:
      value : [any]
    """

    widget_type = "list"

    element_type: str | type[Widget]
    element_name: object
    args: dict[str, Any]
    added_elements_widget: HiddenWidget
    add_button: SubmitButtonWidget
    element_widgets: list[Widget]
    element_count: int

    def __init__(
        self,
        name: str,
        value: list[object] | None = None,
        element_type: str | type[Widget] | None = None,
        element_name: str | htmltext = "row",
        **args: Any,
    ) -> None:
        assert value is None or type(value) is ListType, (
            "form value '%s' not a list: got %r" % (name, value)
        )
        assert type(element_name) in (
            StringType,
            htmltext,
        ), "form value '%s' element_name not a string: got %r" % (
            name,
            element_name,
        )

        Widget.__init__(self, name, value)

        if element_type is None:
            self.element_type = "string"
        else:
            self.element_type = element_type
        self.args = args

        self.added_elements_widget = cast(
            HiddenWidget,
            self.create_subwidget("hidden", "added_elements"),
        )

        added_elements = int(
            str(self.added_elements_widget.get_current_value() or '1')
        )

        self.add_button = cast(
            SubmitButtonWidget,
            self.create_subwidget(
                "submit_button", "add_element", value="Add %s" % element_name
            ),
        )

        if self.add_button.is_submitted():
            added_elements += 1
            self.added_elements_widget.set_current_value(str(added_elements))

        self.element_widgets: list[Widget] = []
        self.element_count = 0

        if isinstance(self.value, list):
            for element in self.value:
                self.add_element(element)

        for _index in range(added_elements):
            self.add_element()

    def add_element(self, value: object | None = None) -> None:
        self.element_widgets.append(
            self.create_subwidget(
                self.element_type,
                "element_%d" % self.element_count,
                value=value,
                **self.args,
            )
        )
        self.element_count += 1

    def render(self, request: HTTPRequest) -> Rendered:
        tags: list[Rendered] = []
        for element_widget in self.element_widgets:
            tags.append(element_widget.render(request))
        tags.append(self.add_button.render(request))
        tags.append(self.added_elements_widget.render(request))
        return htmltext('<br />\n').join(tags)

    def parse(self, request: HTTPRequest) -> object | None:
        self.value = []
        for element_widget in self.element_widgets:
            value = element_widget.parse(request)
            if value is not None:
                self.value.append(value)
        self.value = self.value or None
        return self.value


class CollapsibleListWidget(ListWidget):
    """Widget for lists of objects with associated delete buttons.

    CollapsibleListWidget behaves like ListWidget except that each element
    is rendered with an associated delete button.  Pressing the delete
    button will cause the associated element name to be added to a hidden
    widget that remembers all deletions until the form is submitted.
    Only elements that are not marked as deleted will be rendered and
    ultimately added to the value of the widget.

    Instance attributes:
      value : [any]
    """

    widget_type = "collapsible_list"

    deleted_elements_widget: HiddenWidget
    element_delete_buttons: list[SubmitButtonWidget]
    deleted_elements: str

    def __init__(
        self,
        name: str,
        value: list[object] | None = None,
        element_name: str | htmltext = "row",
        **args: Any,
    ) -> None:
        self.name = name
        self.element_name = element_name
        self.deleted_elements_widget = cast(
            HiddenWidget,
            self.create_subwidget("hidden", "deleted_elements"),
        )
        self.element_delete_buttons: list[SubmitButtonWidget] = []
        self.deleted_elements = str(
            self.deleted_elements_widget.get_current_value() or ''
        )
        ListWidget.__init__(
            self, name, value=value, element_name=element_name, **args
        )

    def add_element(self, value: object | None = None) -> None:
        element_widget_name = "element_%d" % self.element_count
        if self.deleted_elements.find(element_widget_name) == -1:
            delete_button = cast(
                SubmitButtonWidget,
                self.create_subwidget(
                    "submit_button",
                    "delete_" + element_widget_name,
                    value="Delete %s" % self.element_name,
                ),
            )
            if delete_button.is_submitted():
                self.element_count += 1
                self.deleted_elements += element_widget_name
                self.deleted_elements_widget.set_current_value(
                    self.deleted_elements
                )
            else:
                self.element_delete_buttons.append(delete_button)
                ListWidget.add_element(self, value=value)
        else:
            self.element_count += 1

    def render(self, request: HTTPRequest) -> Rendered:
        tags: list[Rendered] = []
        for element_widget, element_delete_button in zip(
            self.element_widgets, self.element_delete_buttons
        ):
            if self.deleted_elements.find(element_widget.name) == -1:
                tags.append(
                    element_widget.render(request)
                    + element_delete_button.render(request)
                )
        tags.append(self.add_button.render(request))
        tags.append(self.added_elements_widget.render(request))
        tags.append(self.deleted_elements_widget.render(request))
        return htmltext('<br />\n').join(tags)
