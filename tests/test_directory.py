"""Tests for the Directory traversal protocol.

Traversal hits are pure (no publisher needed).  Traversal misses raise
TraversalError, whose bare constructor reads the current request path,
so those tests run inside a request context.
"""

from collections.abc import Iterator

import pytest
from helpers import call, request_context

import quixote
from quixote.directory import (
    AccessControlled,
    Directory,
    Resolving,
    export,
    subdir,
)
from quixote.errors import AccessError, TraversalError
from quixote.publish import Publisher
from quixote.wsgi import QWIP


class Sub(Directory):
    _q_exports = ['', 'greet']

    def _q_index(self) -> str:
        return 'sub index'

    def greet(self) -> str:
        return 'hello from sub'


class Root(Directory):
    _q_exports = ['', 'greet', 'motto', ('robots.txt', 'robots_txt'), 'sub']

    motto = 'be kind'

    def __init__(self) -> None:
        self.sub = Sub()

    def _q_index(self) -> str:
        return 'root index'

    def greet(self) -> str:
        return 'hello'

    def robots_txt(self) -> str:
        return 'User-agent: *'


class TestTraversalHits:
    def test_callable_leaf_export_returns_its_result(self) -> None:
        assert Root()._q_traverse(['greet']) == 'hello'

    def test_empty_component_maps_to_q_index(self) -> None:
        assert Root()._q_traverse(['']) == 'root index'

    def test_tuple_export_serves_external_name(self) -> None:
        assert Root()._q_traverse(['robots.txt']) == 'User-agent: *'

    def test_tuple_export_translates_to_internal_name(self) -> None:
        assert Root()._q_translate('robots.txt') == 'robots_txt'

    def test_traversal_recurses_into_nested_directory(self) -> None:
        assert Root()._q_traverse(['sub', 'greet']) == 'hello from sub'

    def test_trailing_empty_component_serves_nested_index(self) -> None:
        assert Root()._q_traverse(['sub', '']) == 'sub index'

    def test_non_callable_leaf_is_returned_as_is(self) -> None:
        assert Root()._q_traverse(['motto']) == 'be kind'

    def test_unexported_attribute_translates_to_none(self) -> None:
        assert Root()._q_translate('robots_txt') is None


class DatabaseIds(Directory):
    _q_exports: list[str | tuple[str, str]] = []

    def _q_lookup(self, component: str, /) -> object | None:
        if component == 'id42':
            return 'record 42'
        return None


class TestDynamicLookup:
    def test_q_lookup_resolves_unexported_component(self) -> None:
        assert DatabaseIds()._q_traverse(['id42']) == 'record 42'

    def test_q_lookup_returning_none_is_not_found(
        self, publisher: Publisher
    ) -> None:
        with request_context(publisher, path='/nope'):
            with pytest.raises(TraversalError):
                DatabaseIds()._q_traverse(['nope'])


class TestTraversalMisses:
    def test_unexported_name_raises_traversal_error_with_path(
        self, publisher: Publisher
    ) -> None:
        with request_context(publisher, path='/oops'):
            with pytest.raises(TraversalError) as exc_info:
                Root()._q_traverse(['oops'])
        assert exc_info.value.status_code == 404
        assert exc_info.value.path == '/oops'

    def test_component_past_a_leaf_raises_traversal_error(
        self, publisher: Publisher
    ) -> None:
        with request_context(publisher, path='/greet/extra'):
            with pytest.raises(TraversalError):
                Root()._q_traverse(['greet', 'extra'])


class Decorated(Directory):
    _q_exports = ['manual']

    manual = 'manual page'

    @export
    def page(self) -> str:
        return 'decorated page'

    @export(name='fancy-name')
    def fancy(self) -> str:
        return 'fancy page'

    @subdir
    def sub(self) -> Sub:
        return Sub()


class TestExportDecorators:
    def test_export_adds_method_name_to_exports(self) -> None:
        assert 'page' in Decorated._q_exports
        assert Decorated()._q_traverse(['page']) == 'decorated page'

    def test_export_with_name_adds_tuple_mapping(self) -> None:
        assert ('fancy-name', 'fancy') in Decorated._q_exports
        assert Decorated()._q_traverse(['fancy-name']) == 'fancy page'

    def test_export_with_non_string_name_raises_type_error(self) -> None:
        def page() -> str:
            return 'page'

        with pytest.raises(TypeError):
            export(name=1)(page)  # type: ignore[arg-type]

    def test_subdir_exports_a_traversable_property(self) -> None:
        assert 'sub' in Decorated._q_exports
        assert Decorated()._q_traverse(['sub', '']) == 'sub index'

    def test_decorator_exports_merge_with_q_exports_list(self) -> None:
        assert 'manual' in Decorated._q_exports
        assert Decorated()._q_traverse(['manual']) == 'manual page'


class LazyDir(Resolving, Directory):
    _q_exports = ['lazy']

    def __init__(self) -> None:
        self.resolve_calls = 0

    def _q_resolve(self, name: str, /) -> object | None:
        self.resolve_calls += 1
        return 'lazy value'


class TestResolving:
    def test_q_resolve_supplies_missing_exported_attribute(self) -> None:
        directory = LazyDir()
        assert directory._q_traverse(['lazy']) == 'lazy value'

    def test_resolved_attribute_is_cached_on_the_instance(self) -> None:
        directory = LazyDir()
        directory._q_traverse(['lazy'])
        directory._q_traverse(['lazy'])
        assert directory.lazy == 'lazy value'  # type: ignore[attr-defined]
        assert directory.resolve_calls == 1


class Guarded(AccessControlled, Directory):
    _q_exports = ['page']

    def __init__(self, allowed: bool) -> None:
        self.allowed = allowed

    def _q_access(self) -> None:
        if not self.allowed:
            raise AccessError

    def page(self) -> str:
        return 'secret'


class TestAccessControlled:
    def test_q_access_raising_blocks_traversal(self) -> None:
        with pytest.raises(AccessError):
            Guarded(allowed=False)._q_traverse(['page'])

    def test_permissive_q_access_allows_traversal(self) -> None:
        assert Guarded(allowed=True)._q_traverse(['page']) == 'secret'


class NoIndex(Directory):
    _q_exports = ['page']

    def page(self) -> str:
        return 'page'


class WSGIRoot(Directory):
    _q_exports = ['', 'sub', 'noindex']

    def __init__(self) -> None:
        self.sub = Sub()
        self.noindex = NoIndex()

    def _q_index(self) -> str:
        return 'root index'


@pytest.fixture
def app() -> Iterator[QWIP]:
    Publisher(WSGIRoot())
    try:
        yield quixote.get_wsgi_app()
    finally:
        quixote.cleanup()


class TestTrailingSlash:
    def test_directory_url_without_slash_redirects(self, app: QWIP) -> None:
        status, headers, _body = call(app, '/sub')
        assert status.startswith('302')
        assert headers['Location'].endswith('/sub/')

    def test_directory_url_with_form_data_is_not_found(
        self, app: QWIP
    ) -> None:
        status, _headers, _body = call(app, '/sub', 'x=1')
        assert status.startswith('404')

    def test_directory_without_index_is_not_found(self, app: QWIP) -> None:
        status, _headers, _body = call(app, '/noindex')
        assert status.startswith('404')
