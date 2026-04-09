#!/usr/bin/env python3
# vim: set ai tw=74 sts=4 sw=4 et:
"""
Convert @ptl_html/@ptl_plain decorated functions to regular Python.
Use -w argument to write files in-place.

PTL functions use an implicit accumulator for expression statements.
This makes the accumulator explicit:
  - Adds `ht = htmltemplate()` preamble
  - Prefixes expression statements with `ht += `
  - Appends `return ht.getvalue()` (if no explicit return)
  - Removes @ptl_html/@ptl_plain decorators
  - Updates imports
"""

import ast
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path


@dataclass
class Modification:
    """A source modification, applied bottom-up to preserve line offsets."""

    line: int  # 1-based line number
    kind: str  # 'delete', 'insert_after', 'prefix'
    text: str = ''
    col: int = 0  # column offset for 'prefix' kind


def find_decorated_functions(tree: ast.Module) -> list[ast.FunctionDef]:
    """Find all FunctionDef nodes with @ptl_html or @ptl_plain decorator,
    at any nesting level."""
    results: list[ast.FunctionDef] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef):
            for dec in node.decorator_list:
                if isinstance(dec, ast.Name) and dec.id in (
                    'ptl_html',
                    'ptl_plain',
                ):
                    results.append(node)
                    break
    return results


def get_decorator_name(func: ast.FunctionDef) -> str:
    """Return 'ptl_html' or 'ptl_plain' for the function's PTL decorator."""
    for dec in func.decorator_list:
        if isinstance(dec, ast.Name) and dec.id in ('ptl_html', 'ptl_plain'):
            return dec.id
    raise ValueError('no PTL decorator found')


def collect_expr_nodes(body: list[ast.stmt]) -> list[ast.Expr]:
    """Collect ast.Expr nodes from a function body, recursing into
    control flow but NOT into nested FunctionDef/ClassDef."""
    exprs: list[ast.Expr] = []

    def visit_body(stmts: list[ast.stmt]) -> None:
        for stmt in stmts:
            if isinstance(stmt, ast.Expr):
                exprs.append(stmt)
            elif isinstance(
                stmt, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)
            ):
                pass  # don't recurse into nested definitions
            elif isinstance(stmt, ast.If):
                visit_body(stmt.body)
                visit_body(stmt.orelse)
            elif isinstance(stmt, (ast.For, ast.While)):
                visit_body(stmt.body)
                visit_body(stmt.orelse)
            elif isinstance(stmt, ast.With):
                visit_body(stmt.body)
            elif isinstance(stmt, ast.Try):
                visit_body(stmt.body)
                for handler in stmt.handlers:
                    visit_body(handler.body)
                visit_body(stmt.orelse)
                visit_body(stmt.finalbody)
            elif isinstance(stmt, ast.TryStar):
                visit_body(stmt.body)
                for handler in stmt.handlers:
                    visit_body(handler.body)
                visit_body(stmt.orelse)
                visit_body(stmt.finalbody)
            elif isinstance(stmt, ast.Match):
                for case in stmt.cases:
                    visit_body(case.body)

    visit_body(body)
    return exprs


def last_line_of_body(body: list[ast.stmt]) -> int:
    """Return the last line number (1-based) of the function body."""
    last = body[-1]
    return last.end_lineno  # type: ignore[return-value]


def body_has_explicit_return(body: list[ast.stmt]) -> bool:
    """Check if the last top-level statement in the body is a Return."""
    return isinstance(body[-1], ast.Return)


def build_modifications(func: ast.FunctionDef) -> list[Modification]:
    """Build all modifications needed for one decorated function."""
    mods: list[Modification] = []
    dec_name = get_decorator_name(func)
    is_html = dec_name == 'ptl_html'

    # 1. Delete decorator line
    for dec in func.decorator_list:
        if isinstance(dec, ast.Name) and dec.id == dec_name:
            mods.append(Modification(line=dec.lineno, kind='delete'))
            break

    # 2. Prefix each expression statement with ht +=
    expr_nodes = collect_expr_nodes(func.body)
    for expr in expr_nodes:
        val = expr.value
        mods.append(
            Modification(
                line=val.lineno,
                kind='prefix',
                col=val.col_offset,
                text='ht += ',
            )
        )

    # Only insert ht preamble and return if ht is actually used
    if expr_nodes:
        # Determine body indentation from first body statement
        body_indent = func.body[0].col_offset
        indent = ' ' * body_indent

        # 3. Insert preamble after the def line
        if is_html:
            preamble = f'{indent}ht = htmltemplate()'
        else:
            preamble = f'{indent}ht = TemplateIO()'
        # The def line is func.lineno; may span multiple lines for complex sigs
        # Insert after the line containing the colon - approximate as func.body[0].lineno - 1
        insert_line = func.body[0].lineno - 1
        mods.append(
            Modification(line=insert_line, kind='insert_after', text=preamble)
        )

        # 4. Append return ht.getvalue() if no explicit return at end
        if not body_has_explicit_return(func.body):
            last_line = last_line_of_body(func.body)
            ret_text = f'{indent}return ht.getvalue()'
            mods.append(
                Modification(
                    line=last_line, kind='insert_after', text=ret_text
                )
            )

    return mods


def apply_modifications(
    lines: list[str], mods: list[Modification]
) -> list[str]:
    """Apply modifications to source lines (0-indexed list).
    Modifications are applied bottom-up to preserve line offsets."""
    # Sort by line descending, with 'prefix' before 'insert_after' at same line,
    # and 'delete' last at same line
    kind_order = {'insert_after': 0, 'prefix': 1, 'delete': 2}
    mods.sort(key=lambda m: (-m.line, kind_order.get(m.kind, 99)))

    for mod in mods:
        idx = mod.line - 1  # convert to 0-based
        if mod.kind == 'delete':
            del lines[idx]
        elif mod.kind == 'insert_after':
            lines.insert(idx + 1, mod.text + '\n')
        elif mod.kind == 'prefix':
            line = lines[idx]
            # Insert 'ht += ' at the column offset
            col = mod.col
            lines[idx] = line[:col] + mod.text + line[col:]

    return lines


def update_imports(source: str) -> str:
    """Add htmltemplate and TemplateIO import."""
    lines = source.split('\n')

    # Insert after last quixote import (handling multi-line imports)
    last_quixote_end = -1
    quixote_re = re.compile(r'^from\s+quixote\b')
    for i, line in enumerate(lines):
        if quixote_re.match(line):
            # Find end of this import (may be multi-line with parens)
            end = i
            if '(' in line and ')' not in line:
                for j in range(i + 1, len(lines)):
                    if ')' in lines[j]:
                        end = j
                        break
            last_quixote_end = end

    if last_quixote_end >= 0:
        lines.insert(
            last_quixote_end + 1,
            'from quixote.html import htmltemplate, TemplateIO',
        )
        return '\n'.join(lines)

    # Fallback: insert after last import
    last_import = -1
    for i, line in enumerate(lines):
        if re.match(r'^\s*(import|from)\s+', line):
            last_import = i
    if last_import >= 0:
        lines.insert(
            last_import + 1,
            'from quixote.html import htmltemplate, TemplateIO',
        )
    return '\n'.join(lines)


# ── Second pass: fix ht += <None-returning call> ──────────────────

BUILTIN_NONE_METHODS: frozenset[str] = frozenset(
    {
        # list
        'append',
        'clear',
        'extend',
        'insert',
        'remove',
        'reverse',
        'sort',
        # dict
        'update',
        # set
        'add',
        'discard',
        'difference_update',
        'intersection_update',
        'symmetric_difference_update',
    }
)


@dataclass
class Fix:
    """One ``ht += …`` site to transform into a bare expression."""

    lineno: int  # 1-based
    target_col: int  # column of ``ht``
    value_col: int  # column of the RHS expression
    call_text: str  # short description for reporting


def _is_none_annotation(node: ast.expr) -> bool:
    """True when *node* represents a ``None`` type annotation."""
    if isinstance(node, ast.Constant) and node.value is None:
        return True
    if isinstance(node, ast.Name) and node.id == 'None':
        return True
    return False


def _has_value_return(body: list[ast.stmt]) -> bool:
    """Recursively check whether *body* contains ``return <expr>``."""
    for stmt in body:
        if isinstance(stmt, ast.Return) and stmt.value is not None:
            return True
        # Recurse into control-flow blocks (but not nested defs).
        for child_body in _child_bodies(stmt):
            if _has_value_return(child_body):
                return True
    return False


def _child_bodies(stmt: ast.stmt) -> list[list[ast.stmt]]:
    """Return the nested statement-lists of *stmt* (not defs/classes)."""
    bodies: list[list[ast.stmt]] = []
    if isinstance(stmt, ast.If):
        bodies += [stmt.body, stmt.orelse]
    elif isinstance(stmt, (ast.For, ast.While)):
        bodies += [stmt.body, stmt.orelse]
    elif isinstance(stmt, ast.With):
        bodies.append(stmt.body)
    elif isinstance(stmt, ast.Try):
        bodies += [stmt.body, stmt.orelse, stmt.finalbody]
        for handler in stmt.handlers:
            bodies.append(handler.body)
    elif isinstance(stmt, ast.TryStar):
        bodies += [stmt.body, stmt.orelse, stmt.finalbody]
        for handler in stmt.handlers:
            bodies.append(handler.body)
    elif isinstance(stmt, ast.Match):
        for case in stmt.cases:
            bodies.append(case.body)
    return bodies


def scan_annotations(
    search_paths: list[str],
    *,
    infer: bool = False,
) -> set[str]:
    """Return function/method names that return None.

    *infer*: also include functions whose bodies never execute
    ``return <value>`` (implicit None).
    """
    # name → [is_none, …] across all definitions seen
    evidence: dict[str, list[bool]] = {}

    for search_path in search_paths:
        path = Path(search_path)
        py_files = sorted(path.rglob('*.py')) if path.is_dir() else [path]

        for py_file in py_files:
            try:
                source = py_file.read_text(encoding='utf-8')
                tree = ast.parse(source, filename=str(py_file))
            except (SyntaxError, UnicodeDecodeError):
                continue
            _collect_from_tree(tree, evidence, infer=infer)

    # A name qualifies only when *every* observed definition is None.
    return {
        name
        for name, verdicts in evidence.items()
        if verdicts and all(verdicts)
    }


def _collect_from_tree(
    tree: ast.Module,
    evidence: dict[str, list[bool]],
    *,
    infer: bool,
) -> None:
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        name = node.name
        if name.startswith('__') and name.endswith('__'):
            continue  # skip dunders

        returns_none: bool | None = None

        # 1. Explicit annotation
        if node.returns is not None:
            returns_none = _is_none_annotation(node.returns)

        # 2. Unannotated functions
        if returns_none is None:
            if infer:
                # With --infer: treat no-return-value as None
                returns_none = not _has_value_return(node.body)
            elif _has_value_return(node.body):
                # Without --infer: still exclude names that visibly
                # return a value (prevents false positives when the
                # same method name returns None in one class but a
                # value in another).
                returns_none = False

        if returns_none is not None:
            evidence.setdefault(name, []).append(returns_none)


def _is_templateio_call(node: ast.expr) -> bool:
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
        return node.func.id in ('htmltemplate', 'TemplateIO')
    return False


def _templateio_vars(tree: ast.Module) -> set[str]:
    """Names assigned from ``htmltemplate()`` / ``TemplateIO()``."""
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            if _is_templateio_call(node.value):
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        names.add(target.id)
    return names


def _call_name(node: ast.Call) -> str | None:
    """Extract the immediate function/method name from a Call node."""
    if isinstance(node.func, ast.Attribute):
        return node.func.attr
    if isinstance(node.func, ast.Name):
        return node.func.id
    return None


def _call_text(node: ast.Call) -> str:
    """Short textual representation for diagnostics."""
    if isinstance(node.func, ast.Attribute):
        if isinstance(node.func.value, ast.Name):
            return f'{node.func.value.id}.{node.func.attr}(…)'
        return f'….{node.func.attr}(…)'
    if isinstance(node.func, ast.Name):
        return f'{node.func.id}(…)'
    return '<call>(…)'


def find_fixes(
    tree: ast.Module,
    none_names: set[str],
) -> list[Fix]:
    """Return fixable ``ht += <none-call>`` sites in *tree*."""
    tio_vars = _templateio_vars(tree)
    fixes: list[Fix] = []

    for node in ast.walk(tree):
        if not isinstance(node, ast.AugAssign):
            continue
        if not isinstance(node.op, ast.Add):
            continue
        if not isinstance(node.target, ast.Name):
            continue
        if node.target.id not in tio_vars:
            continue
        if not isinstance(node.value, ast.Call):
            continue
        name = _call_name(node.value)
        if name is None or name not in none_names:
            continue

        fixes.append(
            Fix(
                lineno=node.target.lineno,
                target_col=node.target.col_offset,
                value_col=node.value.col_offset,
                call_text=_call_text(node.value),
            )
        )

    return fixes


def apply_fixes(lines: list[str], fixes: list[Fix]) -> list[str]:
    """Remove ``ht += `` prefixes in-place (bottom-up)."""
    for fix in sorted(fixes, key=lambda f: -f.lineno):
        idx = fix.lineno - 1
        line = lines[idx]
        lines[idx] = line[: fix.target_col] + line[fix.value_col :]
    return lines


def fix_none_iadd(
    source: str,
    filename: str,
    none_names: set[str],
    *,
    verbose: bool = False,
) -> tuple[str, int]:
    """Strip ``ht += `` from None-returning calls.

    Returns (possibly modified source, number of fixes).
    """
    try:
        tree = ast.parse(source, filename=filename)
    except SyntaxError as exc:
        print(f'  SyntaxError: {exc}', file=sys.stderr)
        return source, 0

    fixes = find_fixes(tree, none_names)
    if not fixes:
        return source, 0

    if verbose:
        for fix in fixes:
            print(
                f'  line {fix.lineno}: ht += {fix.call_text}',
                file=sys.stderr,
            )

    lines = source.splitlines(keepends=True)
    apply_fixes(lines, fixes)
    return ''.join(lines), len(fixes)


def build_none_names(
    search_paths: list[str],
    *,
    infer: bool = False,
    extra: list[str] | None = None,
    verbose: bool = False,
) -> set[str]:
    """Build the combined set of None-returning names."""
    none_names: set[str] = set(BUILTIN_NONE_METHODS)
    if search_paths:
        scanned = scan_annotations(search_paths, infer=infer)
        new = scanned - none_names
        if verbose and new:
            print(
                f'Scanned {len(new)} additional None-returning'
                f' names from annotations/inference'
                f' (use --list-names to see all)',
                file=sys.stderr,
            )
        none_names |= scanned
    if extra:
        none_names.update(extra)
    return none_names


def translate(
    fn: str,
    verbose: bool = False,
    none_names: set[str] | None = None,
) -> tuple[str, int, int]:
    """Translate a file, returning (source, n_converted, n_none_fixed)."""
    with open(fn, encoding='utf-8') as fp:
        source = fp.read()

    tree = ast.parse(source, filename=fn)
    funcs = find_decorated_functions(tree)

    if not funcs:
        if verbose:
            sys.stdout.write(source)
        return source, 0, 0

    # Build all modifications
    all_mods: list[Modification] = []
    for func in funcs:
        all_mods.extend(build_modifications(func))

    # Apply to source lines
    lines = source.splitlines(keepends=True)
    lines = apply_modifications(lines, all_mods)
    result = ''.join(lines)

    # Update imports
    result = update_imports(result)

    # Second pass: fix ht += <none-returning-call>
    n_none_fixed = 0
    if none_names is not None:
        result, n_none_fixed = fix_none_iadd(
            result, fn, none_names, verbose=verbose
        )

    if verbose:
        sys.stdout.write(result)

    return result, len(funcs), n_none_fixed


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(
        description='Convert @ptl_html/@ptl_plain functions to regular Python'
    )
    parser.add_argument(
        '-v',
        '--verbose',
        default=False,
        action='store_true',
        help='write source to stdout',
    )
    parser.add_argument(
        '--write',
        '-w',
        default=False,
        action='store_true',
        help='re-write files',
    )
    # fix-none-iadd options
    parser.add_argument(
        '--no-fix-none',
        action='store_true',
        default=False,
        help='disable second pass that removes ht += for'
        ' None-returning calls',
    )
    parser.add_argument(
        '--search-path',
        action='append',
        default=[],
        metavar='PATH',
        help='directory/file to scan for None-returning'
        ' annotations (repeatable)',
    )
    parser.add_argument(
        '--infer',
        action='store_true',
        help='treat functions with no return-value statement'
        ' as None-returning',
    )
    parser.add_argument(
        '--extra',
        action='append',
        default=[],
        metavar='NAME',
        help='additional function/method name to treat as' ' None-returning',
    )
    parser.add_argument(
        '--list-names',
        action='store_true',
        help='print the None-returning name set and exit',
    )
    parser.add_argument('files', nargs='*')
    args = parser.parse_args()
    if not args.write:
        args.verbose = True

    # Build None-returning names (unless disabled)
    none_names: set[str] | None = None
    if not args.no_fix_none:
        none_names = build_none_names(
            args.search_path,
            infer=args.infer,
            extra=args.extra,
            verbose=args.verbose,
        )

    if args.list_names:
        if none_names is None:
            print('(fix-none pass is disabled)', file=sys.stderr)
        else:
            for name in sorted(none_names):
                print(name)
        return

    if not args.files:
        parser.error('no input files')

    total_converted = 0
    total_none_fixed = 0
    for fn in args.files:
        header = '## %s ' % fn
        header = header.ljust(78, '#')
        print(header, file=sys.stderr)
        src, n_converted, n_none_fixed = translate(
            fn, verbose=args.verbose, none_names=none_names
        )
        print(f'  {n_converted} converted', file=sys.stderr)
        if n_none_fixed:
            print(
                f'  {n_none_fixed} ht+=None fixed',
                file=sys.stderr,
            )
        total_converted += n_converted
        total_none_fixed += n_none_fixed
        if args.write:
            os.rename(fn, fn + '~')
            with open(fn, 'w', encoding='utf-8') as fp:
                fp.write(src)
    if len(args.files) > 1:
        print(
            f'\nTotal: {total_converted} converted,'
            f' {total_none_fixed} ht+=None fixed',
            file=sys.stderr,
        )


if __name__ == '__main__':
    main()
