"""Tests for the Form lifecycle.

Form construction reads the current request (default action) and the
publisher config (form tokens), and `is_submitted`/`has_errors` read the
current request, so most tests run inside a publisher request context.
Pure structural behaviors use `Form(action='/submit', use_tokens=False)`;
a non-empty action and no tokens means construction touches no global
state (a falsy action falls back to the current request's query string).
"""

from collections.abc import Iterator

import pytest
from helpers import request_context

import quixote
from quixote.directory import Directory
from quixote.form.form import Form, FormTokenWidget
from quixote.publish import Publisher
from quixote.session import Session, SessionManager


def plain_form() -> Form:
    """A form that can be built without a publisher or request."""
    return Form(action='/submit', use_tokens=False)


class TestConstruction:
    def test_method_must_be_post_or_get(self) -> None:
        with pytest.raises(ValueError):
            Form(method='put', action='/submit', use_tokens=False)

    def test_enctype_must_be_a_form_encoding(self) -> None:
        with pytest.raises(ValueError):
            Form(action='/submit', use_tokens=False, enctype='text/csv')

    def test_default_action_is_the_query_string(
        self, publisher: Publisher
    ) -> None:
        with request_context(publisher, query='a=1'):
            assert Form(use_tokens=False).action == '?a=1'

    def test_default_action_is_empty_without_a_query(
        self, publisher: Publisher
    ) -> None:
        with request_context(publisher):
            assert Form(use_tokens=False).action == ''


class TestAdd:
    def test_widgets_are_routed_by_kind(self) -> None:
        form = plain_form()
        form.add_string('name')
        form.add_hidden('state', value='x')
        form.add_submit('go', 'Go')
        assert [w.name for w in form.widgets] == ['name']
        assert [w.name for w in form.hidden_widgets] == ['state']
        assert [w.name for w in form.submit_widgets] == ['go']
        assert len(form.get_all_widgets()) == 3

    def test_widget_id_defaults_to_its_name(self) -> None:
        form = plain_form()
        form.add_string('name')
        widget = form.get_widget('name')
        assert widget is not None
        assert widget.attrs['id'] == 'name'

    def test_duplicate_names_are_rejected(self) -> None:
        form = plain_form()
        form.add_string('name')
        with pytest.raises(ValueError):
            form.add_string('name')


class TestIsSubmitted:
    def test_post_form_is_not_submitted_by_a_get_request(
        self, publisher: Publisher
    ) -> None:
        with request_context(publisher, query='a=1') as request:
            request.process_inputs()
            assert Form(use_tokens=False).is_submitted() is False

    def test_post_form_is_submitted_by_a_post_request(
        self, publisher: Publisher
    ) -> None:
        with request_context(publisher, method='POST'):
            assert Form(use_tokens=False).is_submitted() is True

    def test_get_form_is_submitted_by_any_form_data(
        self, publisher: Publisher
    ) -> None:
        with request_context(publisher, query='a=1') as request:
            request.process_inputs()
            form = Form(method='get')
            assert form.is_submitted() is True


class TestFormData:
    def test_submitted_values_are_read_by_widget_name(
        self, publisher: Publisher
    ) -> None:
        with request_context(publisher, method='POST') as request:
            request.form['name'] = 'Alice'
            form = Form(use_tokens=False)
            form.add_string('name')
            assert form['name'] == 'Alice'
            assert form.get('name') == 'Alice'

    def test_unknown_names_raise_or_return_the_default(
        self, publisher: Publisher
    ) -> None:
        with request_context(publisher, method='POST'):
            form = Form(use_tokens=False)
            with pytest.raises(KeyError):
                form['nope']
            assert form.get('nope', 'dflt') == 'dflt'

    def test_force_value_overrides_the_submitted_value(
        self, publisher: Publisher
    ) -> None:
        with request_context(publisher, method='POST') as request:
            request.form['name'] = 'submitted'
            form = Form(use_tokens=False)
            form.add_string('name')
            form.force_value('name', 'forced')
            assert form['name'] == 'forced'


class TestErrors:
    def test_missing_required_field_is_an_error(
        self, publisher: Publisher
    ) -> None:
        with request_context(publisher, method='POST'):
            form = Form(use_tokens=False)
            form.add_string('name', required=True)
            assert form.has_errors() is True
            widget = form.get_widget('name')
            assert widget is not None
            assert widget.error == 'required'

    def test_unsubmitted_form_has_no_errors(
        self, publisher: Publisher
    ) -> None:
        with request_context(publisher):
            form = Form(use_tokens=False)
            form.add_string('name', required=True)
            assert form.has_errors() is False

    def test_set_error_flags_the_form_and_shows_in_render(
        self, publisher: Publisher
    ) -> None:
        with request_context(publisher, method='POST'):
            form = Form(use_tokens=False)
            form.add_string('name')
            form.set_error('name', 'no good')
            assert form.has_errors() is True
            assert 'no good' in str(form.render())

    def test_clear_errors_resets_parse_errors(
        self, publisher: Publisher
    ) -> None:
        with request_context(publisher, method='POST'):
            form = Form(use_tokens=False)
            form.add_string('name', required=True)
            assert form.has_errors() is True
            form.clear_errors()
            assert form.has_errors() is False

    def test_set_error_on_an_unknown_name_is_a_key_error(
        self, publisher: Publisher
    ) -> None:
        with request_context(publisher, method='POST'):
            form = Form(use_tokens=False)
            with pytest.raises(KeyError):
                form.set_error('nope', 'msg')


class TestGetSubmit:
    def test_the_clicked_buttons_name_is_returned(
        self, publisher: Publisher
    ) -> None:
        with request_context(publisher, method='POST') as request:
            request.form['save'] = 'Save'
            form = Form(use_tokens=False)
            form.add_submit('save', 'Save')
            form.add_submit('delete', 'Delete')
            assert form.get_submit() == 'save'

    def test_submission_without_a_known_button_is_true(
        self, publisher: Publisher
    ) -> None:
        with request_context(publisher, method='POST'):
            form = Form(use_tokens=False)
            form.add_submit('save', 'Save')
            assert form.get_submit() is True

    def test_an_unsubmitted_form_returns_false(
        self, publisher: Publisher
    ) -> None:
        with request_context(publisher):
            form = Form(use_tokens=False)
            form.add_submit('save', 'Save')
            assert form.get_submit() is False


class TestRender:
    def test_render_produces_the_expected_form_structure(
        self, publisher: Publisher
    ) -> None:
        with request_context(publisher):
            form = Form(use_tokens=False)
            form.add_hidden('state', value='x')
            form.add_string('name', title='Name')
            form.add_submit('go', 'Go')
            html = str(form.render())
        assert '<form method="post"' in html
        assert 'class="quixote"' in html
        assert html.index('type="hidden"') < html.index('type="text"')
        assert html.index('type="text"') < html.index('<div class="submit">')
        assert html.rstrip().endswith('<br class="quixoteform" />')

    def test_error_notice_appears_when_a_widget_has_an_error(
        self, publisher: Publisher
    ) -> None:
        with request_context(publisher, method='POST'):
            form = Form(use_tokens=False)
            form.add_string('name', required=True)
            html = str(form.render())
        assert 'There were errors processing your form.' in html


class Root(Directory):
    _q_exports = ['']

    def _q_index(self) -> str:
        return 'index'


@pytest.fixture
def token_publisher() -> Iterator[Publisher]:
    """A publisher configured for form tokens (with a session manager)."""
    pub = Publisher(
        Root(), session_manager=SessionManager(), form_tokens=True
    )
    try:
        yield pub
    finally:
        quixote.cleanup()


class TestFormTokens:
    def test_post_forms_get_a_token_widget_automatically(
        self, token_publisher: Publisher
    ) -> None:
        with request_context(token_publisher) as request:
            request.session = Session(None)
            form = Form()
        widget = form.get_widget(Form.TOKEN_NAME)
        assert isinstance(widget, FormTokenWidget)

    def test_render_stores_a_fresh_token_in_the_session(
        self, token_publisher: Publisher
    ) -> None:
        with request_context(token_publisher) as request:
            session = Session(None)
            request.session = session
            form = Form()
            html = str(form.render())
            widget = form.get_widget(Form.TOKEN_NAME)
            assert widget is not None
            token = widget.value
        assert isinstance(token, str)
        assert session.has_form_token(token) is True
        assert token in html

    def test_a_valid_token_is_accepted_and_consumed(
        self, token_publisher: Publisher
    ) -> None:
        with request_context(token_publisher, method='POST') as request:
            session = Session(None)
            request.session = session
            token = session.create_form_token()
            request.form[Form.TOKEN_NAME] = token
            form = Form()
            assert form.has_errors() is False
        assert session.has_form_token(token) is False

    def test_a_bogus_token_shows_the_token_notice(
        self, token_publisher: Publisher
    ) -> None:
        with request_context(token_publisher, method='POST') as request:
            request.session = Session(None)
            request.form[Form.TOKEN_NAME] = 'bogus'
            form = Form()
            assert form.has_errors() is True
            html = str(form.render())
        assert 'The form you have submitted is invalid.' in html
