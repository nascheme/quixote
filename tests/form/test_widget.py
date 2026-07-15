"""Tests for the form widget classes.

Widgets accept an explicit request in `parse(request=...)`, so all tests
here run against a synthetic HTTPRequest with a populated form -- no
publisher is needed.  Render tests parse first (with an unsubmitted GET
request when the value should be the initial one) because `render`
triggers parsing to display errors.
"""

import pytest
from helpers import make_request

from quixote.form.widget import (
    ButtonWidget,
    CheckboxWidget,
    CompositeWidget,
    FileWidget,
    FloatWidget,
    HiddenWidget,
    IntWidget,
    MultipleSelectWidget,
    NumberWidget,
    OptionSelectWidget,
    PasswordWidget,
    RadiobuttonsWidget,
    ResetWidget,
    SelectWidget,
    SingleSelectWidget,
    StringWidget,
    SubmitWidget,
    TextWidget,
    Widget,
    WidgetValueError,
    merge_attrs,
    subname,
)
from quixote.http_request import HTTPRequest, Upload


class TestHelpers:
    def test_subname_joins_with_a_dollar_sign(self) -> None:
        assert subname('form', 'field') == 'form$field'

    def test_merge_attrs_strips_trailing_underscores(self) -> None:
        attrs = merge_attrs({'class_': 'x'}, {'size': 3})
        assert attrs == {'class': 'x', 'size': 3}

    def test_merge_attrs_overrides_win(self) -> None:
        assert merge_attrs({'size': 1}, {'size': 2}) == {'size': 2}


class TestAbstractWidgets:
    @pytest.mark.parametrize('cls', [Widget, SelectWidget, NumberWidget])
    def test_abstract_widget_classes_cannot_be_instantiated(
        self, cls: type[Widget]
    ) -> None:
        with pytest.raises(AssertionError):
            cls('w')


class TestParsing:
    def test_submitted_value_is_parsed_from_the_form(self) -> None:
        widget = StringWidget('w')
        assert widget.parse(request=make_request({'w': 'hi'})) == 'hi'

    def test_blank_submission_parses_to_none(self) -> None:
        widget = StringWidget('w')
        assert widget.parse(request=make_request({'w': '   '})) is None

    def test_missing_required_value_sets_the_required_error(self) -> None:
        widget = StringWidget('w', required=True)
        request = make_request({'other': 'x'})
        assert widget.parse(request=request) is None
        assert widget.get_error(request=request) == 'required'

    def test_unsubmitted_form_keeps_the_initial_value(self) -> None:
        widget = StringWidget('w', value='initial', required=True)
        request = make_request(method='GET')
        assert widget.parse(request=request) == 'initial'
        assert widget.has_error(request=request) is False

    def test_parse_runs_at_most_once(self) -> None:
        widget = StringWidget('w')
        request = make_request({'w': 'first'})
        widget.parse(request=request)
        request.form['w'] = 'second'
        assert widget.parse(request=request) == 'first'

    def test_widget_value_error_becomes_the_widget_error(self) -> None:
        class PickyWidget(StringWidget):
            def _parse(self, request: HTTPRequest) -> None:
                raise WidgetValueError('not to my taste')

        widget = PickyWidget('w')
        request = make_request({'w': 'x'})
        assert widget.get_error(request=request) == 'not to my taste'

    def test_clear_error_discards_the_parse_error(self) -> None:
        widget = StringWidget('w', required=True)
        request = make_request({})
        widget.clear_error(request=request)
        assert widget.has_error(request=request) is False


class TestRenderDecoration:
    def test_render_wraps_the_control_with_titled_divs(self) -> None:
        widget = StringWidget(
            'w', title='Name', hint='Your name', required=True
        )
        widget.parse(request=make_request(method='GET'))
        html = str(widget.render())
        assert 'class="StringWidget widget"' in html
        assert '<div class="title">Name' in html
        assert '<span class="required">*</span>' in html
        assert '<div class="hint">Your name</div>' in html

    def test_render_shows_the_parse_error(self) -> None:
        widget = StringWidget('w', required=True)
        widget.parse(request=make_request({}))
        assert '<div class="error">required</div>' in str(widget.render())


class TestStringWidget:
    def test_renders_a_text_input_with_the_value(self) -> None:
        widget = StringWidget('w', value='hi')
        html = str(widget.render_content())
        assert 'type="text"' in html
        assert 'name="w"' in html
        assert 'value="hi"' in html

    def test_markup_in_the_value_is_escaped(self) -> None:
        widget = StringWidget('w', value='<x>')
        assert 'value="&lt;x&gt;"' in str(widget.render_content())


class TestPasswordWidget:
    def test_renders_a_password_input(self) -> None:
        html = str(PasswordWidget('w').render_content())
        assert 'type="password"' in html


class TestTextWidget:
    def test_renders_a_textarea_with_escaped_body(self) -> None:
        html = str(TextWidget('w', value='a < b').render_content())
        assert html.startswith('<textarea name="w"')
        assert 'a &lt; b' in html
        assert html.endswith('</textarea>')

    def test_parse_normalizes_crlf_to_lf(self) -> None:
        widget = TextWidget('w')
        request = make_request({'w': 'one\r\ntwo'})
        assert widget.parse(request=request) == 'one\ntwo'


class TestCheckboxWidget:
    def test_parses_to_true_when_the_name_is_submitted(self) -> None:
        widget = CheckboxWidget('w')
        assert widget.parse(request=make_request({'w': 'yes'})) is True

    def test_parses_to_false_when_the_name_is_absent(self) -> None:
        widget = CheckboxWidget('w')
        assert widget.parse(request=make_request({'other': '1'})) is False

    def test_renders_checked_only_when_the_value_is_true(self) -> None:
        assert 'checked' in str(
            CheckboxWidget('w', value=True).render_content()
        )
        assert 'checked' not in str(
            CheckboxWidget('w', value=False).render_content()
        )


OPTIONS = [(1, 'one', 'one-key'), (2, 'two', 'two-key')]


class TestSingleSelectWidget:
    def test_options_are_required(self) -> None:
        with pytest.raises(ValueError):
            SingleSelectWidget('w', options=[])

    def test_submitted_key_maps_back_to_the_option_value(self) -> None:
        widget = SingleSelectWidget('w', options=OPTIONS)
        request = make_request({'w': 'two-key'})
        assert widget.parse(request=request) == 2

    def test_unknown_key_is_a_selection_error(self) -> None:
        widget = SingleSelectWidget('w', options=OPTIONS)
        request = make_request({'w': 'bogus'})
        assert widget.parse(request=request) is None
        assert (
            widget.get_error(request=request)
            == SingleSelectWidget.SELECTION_ERROR
        )

    def test_multiple_values_are_a_selection_error(self) -> None:
        widget = SingleSelectWidget('w', options=OPTIONS)
        request = make_request({'w': ['one-key', 'two-key']})
        widget.parse(request=request)
        assert (
            widget.get_error(request=request)
            == SingleSelectWidget.MULTIPLE_SELECTION_ERROR
        )

    def test_set_value_ignores_a_value_that_is_not_an_option(self) -> None:
        widget = SingleSelectWidget('w', options=OPTIONS)
        widget.set_value(3)
        assert widget.value is None
        widget.set_value(2)
        assert widget.value == 2

    def test_render_marks_the_selected_option(self) -> None:
        widget = SingleSelectWidget('w', value=2, options=OPTIONS)
        html = str(widget.render_content())
        assert '<option value="two-key" selected="selected">two' in html
        assert '<option value="one-key">one' in html

    def test_duplicate_descriptions_without_keys_are_rejected(self) -> None:
        with pytest.raises(ValueError):
            SingleSelectWidget('w', options=['same', 'same'])


class TestRadiobuttonsWidget:
    def test_renders_one_radio_input_per_option(self) -> None:
        widget = RadiobuttonsWidget('w', options=['a', 'b'], delim='|')
        html = str(widget.render_content())
        assert html.count('type="radio"') == 2
        assert '|' in html

    def test_the_selected_option_is_checked(self) -> None:
        widget = RadiobuttonsWidget('w', value='b', options=['a', 'b'])
        html = str(widget.render_content())
        checked = [
            line for line in html.splitlines() if 'checked' in line
        ]
        assert len(checked) == 1
        assert 'value="b"' in checked[0]


MANY_OPTIONS = [
    (1, 'one', 'k1'),
    (2, 'two', 'k2'),
    (3, 'three', 'k3'),
]


class TestMultipleSelectWidget:
    def test_submitted_keys_map_to_a_list_of_values(self) -> None:
        widget = MultipleSelectWidget('w', options=MANY_OPTIONS)
        request = make_request({'w': ['k1', 'k3']})
        assert widget.parse(request=request) == [1, 3]

    def test_a_single_submitted_key_yields_a_one_element_list(self) -> None:
        widget = MultipleSelectWidget('w', options=MANY_OPTIONS)
        request = make_request({'w': 'k2'})
        assert widget.parse(request=request) == [2]

    def test_set_value_keeps_only_allowed_values(self) -> None:
        widget = MultipleSelectWidget('w', options=MANY_OPTIONS)
        widget.set_value([1, 99])
        assert widget.value == [1]


class TestOptionSelectWidget:
    def test_parse_defaults_to_the_first_option(self) -> None:
        widget = OptionSelectWidget('w', options=['a', 'b'])
        request = make_request(method='GET')
        assert widget.parse(request=request) == 'a'

    def test_submitted_key_wins_over_the_default(self) -> None:
        widget = OptionSelectWidget('w', options=['a', 'b'])
        request = make_request({'w': 'b'})
        assert widget.parse(request=request) == 'b'


class TestNumberWidgets:
    def test_int_widget_parses_an_integer(self) -> None:
        widget = IntWidget('w')
        assert widget.parse(request=make_request({'w': '42'})) == 42

    def test_int_widget_flags_non_integer_input(self) -> None:
        widget = IntWidget('w')
        request = make_request({'w': 'x'})
        widget.parse(request=request)
        assert widget.get_error(request=request) == 'must be an integer'

    def test_float_widget_parses_a_float(self) -> None:
        widget = FloatWidget('w')
        assert widget.parse(request=make_request({'w': '3.5'})) == 3.5

    def test_float_widget_flags_non_numeric_input(self) -> None:
        widget = FloatWidget('w')
        request = make_request({'w': 'x'})
        widget.parse(request=request)
        assert widget.get_error(request=request) == 'must be a number'

    def test_initial_value_must_match_the_number_type(self) -> None:
        with pytest.raises(AssertionError):
            IntWidget('w', value='42')  # type: ignore[arg-type]


class TestButtonWidgets:
    @pytest.mark.parametrize(
        'cls,html_type',
        [
            (ButtonWidget, 'button'),
            (SubmitWidget, 'submit'),
            (ResetWidget, 'reset'),
        ],
    )
    def test_constructor_value_becomes_the_button_label(
        self, cls: type[ButtonWidget], html_type: str
    ) -> None:
        html = str(cls('go', value='Go!').render_content())
        assert 'type="%s"' % html_type in html
        assert 'value="Go!"' in html

    def test_parses_to_true_only_when_clicked(self) -> None:
        clicked = SubmitWidget('go', value='Go!')
        assert clicked.parse(request=make_request({'go': 'Go!'})) is True
        idle = SubmitWidget('go', value='Go!')
        assert idle.parse(request=make_request({'other': 'x'})) is False


class TestHiddenWidget:
    def test_renders_without_decoration(self) -> None:
        widget = HiddenWidget('w', value='state')
        html = str(widget.render())
        assert html == str(widget.render_content())
        assert 'type="hidden"' in html
        assert 'value="state"' in html

    def test_cannot_hold_an_error(self) -> None:
        widget = HiddenWidget('w')
        with pytest.raises(TypeError):
            widget.set_error('nope')
        widget.set_error(None)


class TestFileWidget:
    def test_parses_the_upload_from_the_form(self) -> None:
        upload = Upload('f.txt')
        widget = FileWidget('f')
        request = make_request({'f': upload})
        assert widget.parse(request=request) is upload

    def test_a_plain_string_is_not_an_upload(self) -> None:
        widget = FileWidget('f')
        assert widget.parse(request=make_request({'f': 'text'})) is None


class TestCompositeWidget:
    def make_address(self) -> CompositeWidget:
        widget = CompositeWidget('addr')
        widget.add(StringWidget, 'street')
        widget.add(StringWidget, 'city', required=True)
        return widget

    def test_children_get_dollar_prefixed_names(self) -> None:
        widget = self.make_address()
        street = widget.get_widget('street')
        assert street is not None
        assert street.get_name() == 'addr$street'

    def test_child_values_are_reached_by_bare_name(self) -> None:
        widget = self.make_address()
        request = make_request(
            {'addr$street': 'Main St', 'addr$city': 'Springfield'}
        )
        widget.parse(request=request)
        assert widget['street'] == 'Main St'
        assert widget.get('city') == 'Springfield'
        assert widget.get('missing') is None

    def test_duplicate_child_names_are_rejected(self) -> None:
        widget = self.make_address()
        with pytest.raises(ValueError):
            widget.add(StringWidget, 'street')

    def test_a_child_error_makes_the_composite_erroneous(self) -> None:
        widget = self.make_address()
        request = make_request({'addr$street': 'Main St'})
        assert widget.has_error(request=request) is True
