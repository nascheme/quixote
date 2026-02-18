#!/usr/bin/env python3
# vim: set ai tw=74 sts=4 sw=4 et:
#
# Convert @ptl_html/@ptl_plain decorated functions to regular Python.
# Use -w argument to write files in-place.
#
# PTL functions use an implicit accumulator for expression statements.
# This makes the accumulator explicit:
#   - Adds `ht = htmltemplate()` preamble
#   - Prefixes expression statements with `ht += `
#   - Appends `return ht.getvalue()` (if no explicit return)
#   - Removes @ptl_html/@ptl_plain decorators
#   - Updates imports

import ast
import os
import re
import sys
from dataclasses import dataclass


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


def translate(fn: str, verbose: bool = False) -> tuple[str, int]:
    """Translate a file, returning (source, n_converted)."""
    with open(fn, encoding='utf-8') as fp:
        source = fp.read()

    tree = ast.parse(source, filename=fn)
    funcs = find_decorated_functions(tree)

    if not funcs:
        if verbose:
            sys.stdout.write(source)
        return source, 0

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

    if verbose:
        sys.stdout.write(result)

    return result, len(funcs)


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
    parser.add_argument('files', nargs='+')
    args = parser.parse_args()
    if not args.write:
        args.verbose = True
    total_converted = 0
    for fn in args.files:
        header = '## %s ' % fn
        header = header.ljust(78, '#')
        print(header, file=sys.stderr)
        src, n_converted = translate(fn, verbose=args.verbose)
        print(f'  {n_converted} converted', file=sys.stderr)
        total_converted += n_converted
        if args.write:
            os.rename(fn, fn + '~')
            with open(fn, 'w', encoding='utf-8') as fp:
                fp.write(src)
    if len(args.files) > 1:
        print(f'\nTotal: {total_converted} converted', file=sys.stderr)


if __name__ == '__main__':
    main()
