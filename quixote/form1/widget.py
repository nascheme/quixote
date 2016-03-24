"""Provides the basic web widget classes: Widget itself, plus StringWidget,
TextWidget, CheckboxWidget, etc.
"""

import struct
from types import FloatType, IntType, ListType, StringType, TupleType
from quixote import get_request
from quixote.html import htmltext, htmlescape, htmltag
from quixote.http_request import Upload


class FormValueError (Exception):
    """Raised whenever a widget has problems parsing its value."""

    def __init__(self, msg):
        self.msg = msg


    def __str__(self):
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
    widget_type = None

    def __init__(self, name, value=None):
        assert self.__class__ is not Widget, "abstract class"
        self.set_name(name)
        self.set_value(value)


    def __repr__(self):
        return "<%s at %x: %s>" % (self.__class__.__name__,
                                   id(self),
                                   self.name)


    def __str__(self):
        return "%s: %s" % (self.widget_type, self.name)


    def set_name(self, name):
        self.name = name


    def set_value(self, value):
        self.value = value


    def clear(self):
        self.value = None

    # -- Subclasses must implement these -------------------------------

    def render(self, request):
        """render(request) -> HTML text"""
        raise NotImplementedError


    def parse(self, request):
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
    def get_subwidget_name(self, name):
        return "%s$%s" % (self.name, name)


    def create_subwidget(self, widget_type, widget_name, value=None, **args):
        from quixote.form.form import get_widget_class
        klass = get_widget_class(widget_type)
        name = self.get_subwidget_name(widget_name)
        return klass(*(name, value), **args)

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

class StringWidget (Widget):
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

    def __init__(self, name, value=None,
                 size=None, maxlength=None):
        Widget.__init__(self, name, value)
        self.size = size
        self.maxlength = maxlength


    def render(self, request, **attributes):
        return htmltag("input", xml_end=1,
                       type=self.html_type,
                       name=self.name,
                       size=self.size,
                       maxlength=self.maxlength,
                       value=self.value,
                       **attributes)


class FileWidget (StringWidget):
    """Trivial subclass of StringWidget for uploading files.

    Instance attributes: none
    """
    widget_type = "file"
    html_type = "file"

    def parse(self, request):
        """parse(request) -> any"""
        value = request.form.get(self.name)
        if isinstance(value, Upload):
            self.value = value
        else:
            self.value = None
        return self.value


class PasswordWidget (StringWidget):
    """Trivial subclass of StringWidget for entering passwords (different
    widget type because HTML does it that way).

    Instance attributes: none
    """

    widget_type = "password"
    html_type = "password"


class TextWidget (Widget):
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

    def __init__(self, name, value=None, cols=None, rows=None, wrap=None,
                 css_class=None):
        Widget.__init__(self, name, value)
        self.cols = cols
        self.rows = rows
        self.wrap = wrap
        self.css_class = css_class

    def render(self, request):
        return (htmltag("textarea", name=self.name,
                        cols=self.cols,
                        rows=self.rows,
                        wrap=self.wrap,
                        css_class=self.css_class) +
                htmlescape(self.value or "") +
                htmltext("</textarea>"))


    def parse(self, request):
        value = Widget.parse(self, request)
        if value:
            value = value.replace("\r\n", "\n")
            self.value = value
        return self.value


class CheckboxWidget (Widget):
    """Widget for a single checkbox: corresponds to "<input
    type=checkbox>".  Do not put multiple CheckboxWidgets with the same
    name in the same form.

    Instance attributes:
      value : boolean
    """

    widget_type = "checkbox"

    def render(self, request):
        return htmltag("input", xml_end=1,
                       type="checkbox",
                       name=self.name,
                       value="yes",
                       checked=self.value and "checked" or None)


    def parse(self, request):
        self.value = self.name in request.form
        return self.value


class SelectWidget (Widget):
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

    def __init__(self, name, value=None,
                 allowed_values=None,
                 descriptions=None,
                 options=None,
                 size=None,
                 sort=0,
                 verify_selection=1):
        assert self.__class__ is not SelectWidget, "abstract class"
        self.options = []
        # if options passed, cannot pass allowed_values or descriptions
        if allowed_values is not None:
            assert options is None, (
                'cannot pass both allowed_values and options')
            assert allowed_values, (
                'cannot pass empty allowed_values list')
            self.set_allowed_values(allowed_values, descriptions, sort)
        elif options is not None:
            assert descriptions is None, (
                'cannot pass both options and descriptions')
            assert options, (
                'cannot pass empty options list')
            self.set_options(options, sort)
        self.set_name(name)
        self.set_value(value)
        self.size = size
        self.verify_selection = verify_selection


    def get_allowed_values(self):
        return [item[0] for item in self.options]


    def get_descriptions(self):
        return [item[1] for item in self.options]


    def set_value(self, value):
        self.value = None
        for object, description, key in self.options:
            if value == object:
                self.value = value
                break


    def _generate_keys(self, values, descriptions):
        """Called if no keys were provided.  Try to generate a set of keys
        that will be consistent between rendering and parsing.
        """
        # try to use ZODB object IDs
        keys = []
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
        used_keys = {}
        keys = list(map(str, descriptions))
        for key in keys:
            if key in used_keys:
                raise ValueError("duplicated descriptions (provide keys)")
            used_keys[key] = 1
        return keys


    def set_options(self, options, sort=0):
        """(options: [objects:any], sort=0)
         or
           (options: [(object:any, description:any)], sort=0)
         or
           (options: [(object:any, description:any, key:any)], sort=0)
        """

        """
        Set the options list.  The list of options can be a list of objects, in
        which case the descriptions default to map(htmlescape, objects)
        applying htmlescape() to each description and
        key.
        If keys are provided they must be distinct.  If the sort keyword
        argument is true, sort the options by case-insensitive lexicographic
        order of descriptions, except that options with value None appear
        before others.
        """
        if options:
            first = options[0]
            values = []
            descriptions = []
            keys = []
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
                values = descriptions = options

            if not keys:
                keys = self._generate_keys(values, descriptions)

            options = list(zip(values, descriptions, keys))

            if sort:
                def make_sort_key(option):
                    value, description, key = option
                    if value is None:
                        return ('', option)
                    else:
                        return (str(description).lower(), option)
                doptions = sorted(map(make_sort_key, options))
                options = [item[1] for item in doptions]
        self.options = options


    def parse_single_selection(self, parsed_key):
        for value, description, key in self.options:
            if key == parsed_key:
                return value
        else:
            if self.verify_selection:
                raise FormValueError("invalid value selected")
            else:
                return self.options[0][0]


    def set_allowed_values(self, allowed_values, descriptions=None, sort=0):
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


    def is_selected(self, value):
        return value == self.value


    def render(self, request):
        if self.widget_type == "multiple_select":
            multiple = "multiple"
        else:
            multiple = None
        if self.widget_type == "option_select":
            onchange = "submit()"
        else:
            onchange = None
        tags = [htmltag("select", name=self.name,
                        multiple=multiple, onchange=onchange,
                        size=self.size)]
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


class SingleSelectWidget (SelectWidget):
    """Widget for single selection.
    """

    widget_type = "single_select"

    def parse(self, request):
        parsed_key = request.form.get(self.name)
        self.value = None
        if parsed_key:
            if type(parsed_key) is ListType:
                raise FormValueError("cannot select multiple values")
            self.value = self.parse_single_selection(parsed_key)
        return self.value


class RadiobuttonsWidget (SingleSelectWidget):
    """Widget for a *set* of related radiobuttons -- all have the
    same name, but different values (and only one of those values
    is returned by the whole group).

    Instance attributes:
      delim : string = None
        string to emit between each radiobutton in the group.  If
        None, a single newline is emitted.
    """

    widget_type = "radiobuttons"

    def __init__(self, name, value=None,
                 allowed_values=None,
                 descriptions=None,
                 options=None,
                 delim=None):
        SingleSelectWidget.__init__(self, name, value, allowed_values,
                                    descriptions, options)
        if delim is None:
            self.delim = "\n"
        else:
            self.delim = delim


    def render(self, request):
        tags = []
        for object, description, key in self.options:
            if self.is_selected(object):
                checked = "checked"
            else:
                checked = None
            r = htmltag("input", xml_end=True,
                        type="radio",
                        name=self.name,
                        value=key,
                        checked=checked)
            tags.append(r + htmlescape(description))
        return htmlescape(self.delim).join(tags)


class MultipleSelectWidget (SelectWidget):
    """Widget for multiple selection.

    Instance attributes:
      value : [any]
        for multipe selects, the value is None or a list of
        elements from dict(self.options).values()
    """

    widget_type = "multiple_select"

    def set_value(self, value):
        allowed_values = self.get_allowed_values()
        if value in allowed_values:
            self.value = [ value ]
        elif type(value) in (ListType, TupleType):
            self.value = [ element
                           for element in value
                           if element in allowed_values ] or None
        else:
            self.value = None


    def is_selected(self, value):
        if self.value is None:
            return value is None
        else:
            return value in self.value


    def parse(self, request):
        parsed_keys = request.form.get(self.name)
        self.value = None
        if parsed_keys:
            if type(parsed_keys) is ListType:
                self.value =  [value
                               for value, description, key in self.options
                               if key in parsed_keys] or None
            else:
                self.value = [self.parse_single_selection(parsed_keys)]
        return self.value


class SubmitButtonWidget (Widget):
    """
    Instance attributes:
      value : boolean
    """

    widget_type = "submit_button"

    def __init__(self, name=None, value=None):
        Widget.__init__(self, name, value)


    def render(self, request):
        value = (self.value and htmlescape(self.value) or None)
        return htmltag("input", xml_end=1, type="submit",
                       name=self.name, value=value)


    def parse(self, request):
        return request.form.get(self.name)


    def is_submitted(self):
        return self.parse(get_request())


class HiddenWidget (Widget):
    """
    Instance attributes:
      value : string
    """

    widget_type = "hidden"

    def render(self, request):
        if self.value is None:
            value = None
        else:
            value = htmlescape(self.value)
        return htmltag("input", xml_end=1,
                       type="hidden",
                       name=self.name,
                       value=value)


    def set_current_value(self, value):
        self.value = value
        request = get_request()
        if request.form:
            request.form[self.name] = value


    def get_current_value(self):
        request = get_request()
        if request.form:
            return self.parse(request)
        else:
            return self.value

# -- Derived widget types ----------------------------------------------
# (these don't correspond to fundamental widget types in HTML,
# so they're separated)

class NumberWidget (StringWidget):
    """
    Instance attributes: none
    """

    # Parameterize the number type (either float or int) through
    # these class attributes:
    type_object = None                  # eg. int, float
    type_error = None                   # human-readable error message
    type_converter = None               # eg. int(), float()

    def __init__(self, name,
                 value=None,
                 size=None, maxlength=None):
        assert self.__class__ is not NumberWidget, "abstract class"
        assert value is None or type(value) is self.type_object, (
            "form value '%s' not a %s: got %r" % (name,
                                                  self.type_object,
                                                  value))
        StringWidget.__init__(self, name, value, size, maxlength)


    def parse(self, request):
        value = StringWidget.parse(self, request)
        if value:
            try:
                self.value = self.type_converter(value)
            except ValueError:
                raise FormValueError(self.type_error)
        return self.value


class FloatWidget (NumberWidget):
    """
    Instance attributes:
      value : float
    """

    widget_type = "float"
    type_object = FloatType
    type_converter = float
    type_error = "must be a number"


class IntWidget (NumberWidget):
    """
    Instance attributes:
      value : int
    """

    widget_type = "int"
    type_object = IntType
    type_converter = int
    type_error = "must be an integer"


class OptionSelectWidget (SingleSelectWidget):
    """Widget for single selection with automatic submission and early
    parsing.  This widget parses the request when it is created.  This
    allows its value to be used to decide what other widgets need to be
    created in a form.  It's a powerful feature but it can be hard to
    understand what's going on.

    Instance attributes:
      value : any
    """

    widget_type = "option_select"

    def __init__(self, *args, **kwargs):
        SingleSelectWidget.__init__(self, *args, **kwargs)

        request = get_request()
        if request.form:
            SingleSelectWidget.parse(self, request)
        if self.value is None:
            self.value = self.options[0][0]


    def render(self, request):
        return (SingleSelectWidget.render(self, request) +
                htmltext('<noscript>'
                         '<input type="submit" name="" value="apply" />'
                         '</noscript>'))


    def parse(self, request):
        return self.value


    def get_current_option(self):
        return self.value


class ListWidget (Widget):
    """Widget for lists of objects.

    Instance attributes:
      value : [any]
    """

    widget_type = "list"

    def __init__(self, name, value=None,
                 element_type=None,
                 element_name="row",
                 **args):
        assert value is None or type(value) is ListType, (
            "form value '%s' not a list: got %r" % (name, value))
        assert type(element_name) in (StringType, htmltext), (
            "form value '%s' element_name not a string: "
            "got %r" % (name, element_name))

        Widget.__init__(self, name, value)

        if element_type is None:
            self.element_type = "string"
        else:
            self.element_type = element_type
        self.args = args

        self.added_elements_widget = self.create_subwidget(
            "hidden", "added_elements")

        added_elements = int(self.added_elements_widget.get_current_value() or
                             '1')

        self.add_button = self.create_subwidget(
            "submit_button", "add_element",
            value="Add %s" % element_name)

        if self.add_button.is_submitted():
            added_elements += 1
            self.added_elements_widget.set_current_value(str(added_elements))

        self.element_widgets = []
        self.element_count = 0

        if self.value is not None:
            for element in self.value:
                self.add_element(element)

        for index in range(added_elements):
            self.add_element()

    def add_element(self, value=None):
        self.element_widgets.append(
            self.create_subwidget(self.element_type,
                                  "element_%d" % self.element_count,
                                  value=value,
                                  **self.args))
        self.element_count += 1

    def render(self, request):
        tags = []
        for element_widget in self.element_widgets:
            tags.append(element_widget.render(request))
        tags.append(self.add_button.render(request))
        tags.append(self.added_elements_widget.render(request))
        return htmltext('<br />\n').join(tags)

    def parse(self, request):
        self.value = []
        for element_widget in self.element_widgets:
            value = element_widget.parse(request)
            if value is not None:
                self.value.append(value)
        self.value = self.value or None
        return self.value



class CollapsibleListWidget (ListWidget):
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

    def __init__(self, name, value=None, element_name="row", **args):
        self.name = name
        self.element_name = element_name
        self.deleted_elements_widget = self.create_subwidget(
            "hidden", "deleted_elements")
        self.element_delete_buttons = []
        self.deleted_elements = (
            self.deleted_elements_widget.get_current_value() or '')
        ListWidget.__init__(self, name, value=value,
                            element_name=element_name,
                            **args)

    def add_element(self, value=None):
        element_widget_name = "element_%d" % self.element_count
        if self.deleted_elements.find(element_widget_name) == -1:
            delete_button = self.create_subwidget(
                "submit_button", "delete_" + element_widget_name,
                value="Delete %s" % self.element_name)
            if delete_button.is_submitted():
                self.element_count += 1
                self.deleted_elements += element_widget_name
                self.deleted_elements_widget.set_current_value(
                    self.deleted_elements)
            else:
                self.element_delete_buttons.append(delete_button)
                ListWidget.add_element(self, value=value)
        else:
            self.element_count += 1

    def render(self, request):
        tags = []
        for element_widget, element_delete_button in zip(
                self.element_widgets, self.element_delete_buttons):
            if self.deleted_elements.find(element_widget.name) == -1:
                tags.append(element_widget.render(request) +
                            element_delete_button.render(request))
        tags.append(self.add_button.render(request))
        tags.append(self.added_elements_widget.render(request))
        tags.append(self.deleted_elements_widget.render(request))
        return htmltext('<br />\n').join(tags)
