# AGENTS.md

Orientation for agents and developers working in the Quixote repo, or on an
application built on it. Read this first.

Quixote is a small Python web framework: an application maps request URLs onto
Python objects by walking a tree of `Directory` objects, and generates HTML
with the `htmltext` safe-string type, usually through PTL templates.

## Repo conventions

- src layout: the package is `src/quixote/`; the pytest suite lives in the
  top-level `tests/` tree (mirroring the package: `tests/form/`, `tests/html/`,
  `tests/ptl/`). Tests are not part of the package and are not installed.
  `tests/manual/` holds dev-server helpers, not automated tests.
- Python 3.13+, managed with `uv`; run everything through `uv run`.
- `make` runs `check` (ruff lint) then `types` (`pyrefly`); `make format` runs
  ruff format. Keep the project fully type-annotated. Line length 78.
- `make setup` runs `uv sync`: it creates/updates `.venv` with the locked dev
  deps and an editable install of quixote (also builds the C extension). `uv
  run` does this implicitly, so you rarely need to call it directly.
- `make test` runs the pytest suite in `.venv` (depends on `setup`). Equivalent
  to `uv run pytest`. PTL-based test modules need the import hook installed
  first.
- ASCII where it will do (`-`, not an em-dash); no emojis in code, commits, or
  comments.
- Do not commit unless explicitly asked.

## Programming model

The fast path to the framework and any app on it. Read the linked module
docstrings and doc files for the full contract.

- URL traversal and the `_q_*` protocol (`_q_exports`, `_q_index`, `_q_lookup`,
  `_q_traverse`): `src/quixote/directory.py` and `doc/public-api.txt` section 2. The
  core abstraction -- request paths are walked one component at a time down a
  tree of `Directory` instances.
- PTL templates (`@ptl_html` / `@ptl_plain` and the `.ptl` import hook):
  `doc/PTL.txt`, `src/quixote/ptl/`. Call `quixote.enable_ptl()` once at startup,
  before importing any `.ptl` module (and after importing ZODB, if used).
- `htmltext` and the escaping model: `doc/tstring_html.txt`, `src/quixote/html/`.
  `htmltext` marks already-safe HTML and is never auto-escaped; combining it
  with a plain `str` escapes the `str` operand. Convert untrusted text with
  `htmlescape()`.
- Request / response / session accessors (`get_request`, `get_response`,
  `get_session`, `redirect`, ...): `src/quixote/publish.py`, `doc/session-mgmt.txt`.
- Forms and widgets: `doc/widgets.txt`, `src/quixote/form/` (`src/quixote/form1/` is
  legacy).
- Errors and HTTP status (`PublishError` subclasses map to status codes):
  `src/quixote/errors.py`.

## Further documentation

- `doc/public-api.txt` -- inventory of the public API surface.
- Module and class docstrings -- the authoritative, contract-level reference;
  prefer them over the older prose docs.
- `doc/*.txt` -- older reStructuredText guides. The conceptual material
  (widgets, sessions, PTL, static files) is still useful; the wiring/deployment
  docs predate WSGI and are stale -- verify against the code before trusting
  them.

## Gotchas

- `_q_index` is not inherited from `Directory`; a URL-endpoint directory must
  define its own.
- Only names in `_q_exports` (or resolved by `_q_lookup`) are URL-reachable;
  adding a method does not publish it.
- Never wrap untrusted input in `htmltext`; use `htmlescape`.
- `get_request` / `get_response` / `get_session` are valid only during a
  request; they raise `RuntimeError` otherwise.
- There are two `htmltext` implementations -- the C extension (`_c_htmltext`)
  and a pure-Python fallback (`_py_htmltext`); keep them behaviourally
  identical.
