# Quixote 4.0 - Release Notes

This release includes type annotations, a source-tree reorganization, and a
number of internal rewrites. The great majority of the public API is unchanged
and backward-compatible. This document lists the changes that can affect an
existing application, so you can check your code before upgrading.

Changes are grouped by how likely they are to require action:

- **Behavior changes** - stricter or corrected behavior on edge cases; most
  correct code is unaffected.
- **Potential compatibility changes** - stricter signatures that may affect an
  unusual calling style.
- **Not breaking** - noted only to prevent confusion (e.g. newly optional
  arguments).

The only known potentially incompatible changes are the edge cases listed under
behavior changes and the stricter positional-only signatures called out below.

---

## Potential compatibility changes

### Some traversal hooks now use positional-only parameters

`quixote.directory`, `quixote.util`

Several traversal hook methods now mark their path/name argument as
positional-only (`/` in the signature):

- `Directory._q_translate(component)`, `Directory._q_lookup(component)`,
  `Directory._q_traverse(path)`
- `AccessControlled._q_traverse(path)`
- `Resolving._q_resolve(name)`, `Resolving._q_translate(component)`
- `StaticDirectory._q_lookup(name)`
- `StaticBundle._q_traverse(path)`
- `Redirector._q_lookup(component)`

Quixote's traversal code calls these hooks positionally, so normal URL
traversal and ordinary application overrides are unaffected. The potentially
incompatible case is direct application code that calls one of these methods
with a keyword argument, e.g. `directory._q_lookup(component="x")`; call it
positionally instead: `directory._q_lookup("x")`.

## Behavior changes

### `htmltext` formatting rejects the `c` presentation type

`quixote.html.htmltext`, `quixote.html.htmlformat`, PTL HTML f-strings

Escaping-aware formatting now raises `ValueError` when the `c` presentation
code is used. This applies to `%c`, `htmltext('{:c}').format(value)`, PTL HTML
f-strings, and `htmlformat()` t-string interpolations. Previously, an integer
could be converted directly to an arbitrary Unicode character after the
escaping step. For example, formatting `38` as `c` emitted a raw `&`; other
values could emit `<`, `>`, or `"`. That violated the guarantee that ordinary
interpolated values cannot introduce HTML markup characters.

The `c` code is uncommon in HTML templates, so most applications need no
change. If an application intentionally formats a code point, convert it to a
string before interpolation so it follows the normal escaping path:

```python
character = chr(codepoint)
result = htmltext('{}').format(character)
# or: htmlformat(t'{character}')
```

The escaping guarantee is for HTML text and ordinary double-quoted attribute
values. It does not make values safe for URLs, JavaScript, CSS, tag or
attribute names, `srcdoc`, or single-quoted or unquoted attributes. Literal
t-string `Template` parts and values explicitly wrapped in `htmltext` are
trusted markup.

The escaping layer also assumes that application-defined subclasses of
`str`, `int`, and `float` do not override conversion or formatting methods to
return unsafe markup. In-process Python classes are trusted application code,
not hostile client data; this layer is not intended to sandbox malicious
Python objects.

### Request-context accessors: `get_*` return None, new raising `current_*` family

`quixote.publish` (and the re-exports from `quixote`)

The `get_*` accessors keep their pre-4.0 None-returning behavior:
`get_publisher()`, `get_request()`, `Publisher.get_request()`,
`get_response()`, `get_session()`, `get_user()`, and
`get_session_manager()` return `None` when there is no publisher, no
active request, no session, or no user. The common check still works:

```python
if get_request() is None:      # still a valid "are we in a request?" check
    ...
```

One edge case is now more permissive: with no publisher installed at all,
these helpers previously raised `AttributeError`; they now return `None`
there too.

Each accessor gains a `current_*` counterpart that raises
`RuntimeError` instead of returning `None` - `current_publisher()`,
`current_request()`, `current_response()`, `current_session()`,
`current_user()`, `current_session_manager()`. These are convenient in
code that only runs while handling a request (and give non-Optional
types under a type checker).

The request-dependent helpers with no meaningful None result -
`get_field()`, `get_param()`, `get_cookie()`, `get_path()`,
`redirect()`, `get_wsgi_app()` - now raise `RuntimeError` when there is
no active request or publisher; previously they raised `AttributeError`
in that situation. Code that specifically caught `AttributeError` around
them should catch `RuntimeError` instead.

### `randbytes()` default is now 16 bytes (128-bit)

`quixote.util.randbytes`

`randbytes()` called with no argument now returns a 16-byte (128-bit) token
(~22 URL-safe characters). Previously, when the `secrets` module was available
(Python 3.6+, i.e. every supported version), `randbytes` was an alias for
`secrets.token_urlsafe`, whose no-argument default is 32 bytes (~43 characters).
It is now a function with signature `randbytes(n=16)`, making the default
consistent across all three implementation branches.

128 bits is the recommended amount of entropy for opaque tokens and identifiers;
both OWASP and NIST consider it sufficient for that purpose. Quixote's own
session ids and CSRF tokens are unaffected: they have always called
`randbytes(16)` explicitly, so they remain 128-bit, and every call to
`randbytes()` inside the Quixote source passes `16` explicitly.

**Who is affected:** application code that calls `randbytes()` with no argument
gets a shorter string (~22 chars instead of ~43). This is only a concern if you
stored or compared tokens by an assumed length, or specifically require more
than 128 bits. To keep the previous length, pass it explicitly:

```python
token = randbytes(32)          # matches the pre-4.0 no-argument result
```

### `export()` and `subdir()` reject a non-string name with `TypeError`

`quixote.directory`

The `@export(name=...)` and `@subdir(name=...)` decorators now raise
`TypeError` immediately if `name` is not a string. Previously a non-string name
was accepted and either failed later or silently misbehaved. Correct usage
(string names, or no `name` argument) is unaffected. This only surfaces
existing misuse.

### `sendmail()` raises `RuntimeError` when no mail server is configured

`quixote.sendmail.sendmail`

The signature is unchanged. When no `mail_server` argument is given and
`MAIL_SERVER` is not set in the config, `sendmail()` now raises
`RuntimeError("no mail_server supplied, and MAIL_SERVER not set in config
file")` instead of falling through to an SMTP connection to `None` (localhost).
Calls that pass a server or set the config value behave exactly as before.

### `safe_str_cmp()` raises a clean `TypeError` on mixed `str`/`bytes`

`quixote.util.safe_str_cmp`

Comparing a `str` against a `bytes` (in either order) now raises
`TypeError('mixed string and bytes arguments are not allowed')`. Previously such
a call also failed, but incidentally and with an inconsistent exception
(`AttributeError` or `TypeError`) depending on argument order. Correct calls
(both arguments the same type) are unchanged. No action needed unless you were
depending on the old, already-broken behavior.

### `valid_csrf_token()` rejects non-string field values

`quixote.session`

The CSRF check now treats a submitted token that is not a string (e.g. a file
upload or a repeated field arriving as a list) as invalid, instead of proceeding
with it. Normal cases (missing token, matching string token) behave as before.

### Minor: `parse_header()` decoding of `email.header.Header` objects

`quixote.http_request.parse_header`

When passed an `email.header.Header` object, the function now decodes it via
`str(header)` rather than joining raw chunks, which can change how RFC 2047
encoded-word values are rendered. Only relevant if you call `parse_header()`
directly with a `Header` object; passing a plain string (the normal case) is
unaffected.

---

## Not breaking (clarifications)

These changed but remain backward-compatible; listed because they may look like
breaks:

- **`Upload.read(n=-1)`** (`quixote.http_request`): the `n` argument became
  optional (it was required). Existing `upload.read(size)` calls still work;
  `upload.read()` now reads to the end.
- **`SessionManager.get()` / `NullSessionManager.get()`** (`quixote.session`):
  gained an optional `default` argument, matching the mapping `get(key,
  default)` convention. Existing single-argument calls are unchanged.
- **Session `dump()`** now defaults to `sys.stdout` instead of raising when
  called with no file argument (a bug fix, strictly more permissive).

## Source layout (packaging only)

The package source moved from `quixote/` to `src/quixote/`. The import name is
still `quixote`, so `import quixote` and all `from quixote... import ...`
statements are unaffected. This only matters if you build or install Quixote
from a source checkout, or if your tooling referenced the on-disk path.

## HTML templates using t-strings

Version 4 of Quxote includes the ``htmlformat()`` function.  See
``doc/tstring_html.txt`` for information on how this is used and how ``.ptl``
modules can be converted.  Quixote 4.x will continue to support `.ptl` modules.
The t-string approach is provided as a way to get the security benefits of PTL
while still using standard ``.py`` module syntax.
