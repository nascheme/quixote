#!/usr/bin/env python3
# vim: set ai tw=74 sts=4 sw=4 et:
"""
Add/replace return type annotations on @ptl_html decorated functions.
For each function decorated with @ptl_html, ensure the return type
is `-> htmltext`.  Use -w argument to write files in-place.
"""

import ast
import os
import sys


def find_ptl_html_functions(
    tree: ast.Module,
) -> list[ast.FunctionDef]:
    """Find all FunctionDef nodes with @ptl_html decorator."""
    results: list[ast.FunctionDef] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef):
            for dec in node.decorator_list:
                if isinstance(dec, ast.Name) and dec.id == 'ptl_html':
                    results.append(node)
                    break
    return results


def fix_return_type(lines: list[str], func: ast.FunctionDef) -> bool:
    """Fix the return type of a single function.  Returns True if
    a change was made."""
    # Find the line with the def and the closing '):'
    # The def starts at func.lineno (1-based).  The body starts
    # at func.body[0].lineno.  The colon ending the signature is
    # somewhere between.

    # Find the colon that ends the def signature.  We scan backwards
    # from the first body line.
    body_start = func.body[0].lineno  # 1-based
    colon_line_idx = None
    colon_col = None

    for i in range(body_start - 2, func.lineno - 2, -1):
        idx = i  # 0-based line index
        if idx < 0:
            continue
        line = lines[idx]
        # Find last ':' that isn't inside a string
        # Simple approach: find rightmost ':'
        col = line.rstrip('\n').rstrip().rfind(':')
        if col >= 0:
            colon_line_idx = idx
            colon_col = col
            break

    if colon_line_idx is None:
        return False

    line = lines[colon_line_idx]

    if func.returns is not None:
        # There's an existing return annotation - replace it
        # The annotation spans from func.returns to just before
        # the colon.  We need to find '->' and replace from
        # after '->' to colon with ' htmltext'.
        # Search for '->' in the def signature lines
        for search_idx in range(func.lineno - 1, colon_line_idx + 1):
            arrow_pos = lines[search_idx].find('->')
            if arrow_pos >= 0:
                # Check if it's already htmltext
                if (
                    isinstance(func.returns, ast.Name)
                    and func.returns.id == 'htmltext'
                ):
                    return False  # already correct

                if search_idx == colon_line_idx:
                    # Arrow and colon on same line
                    before = lines[search_idx][:arrow_pos]
                    after_colon = lines[colon_line_idx][colon_col:]
                    lines[search_idx] = before + '-> htmltext' + after_colon
                else:
                    # Arrow on different line than colon
                    before = lines[search_idx][:arrow_pos]
                    after_colon = lines[colon_line_idx][colon_col:]
                    # Remove intermediate lines if any
                    for rm_idx in range(colon_line_idx, search_idx, -1):
                        lines[rm_idx] = ''
                    lines[search_idx] = before + '-> htmltext' + after_colon
                return True
        return False
    else:
        # No return annotation - insert -> htmltext before the colon
        before = line[:colon_col]
        after = line[colon_col:]  # includes the ':'
        lines[colon_line_idx] = before + ' -> htmltext' + after
        return True


def add_htmltext_import(source: str, tree: ast.Module) -> str:
    """Insert 'from quixote.html import htmltext' after the last
    top-level import, using the AST to find the correct position."""
    # Check if htmltext is already available as the name 'htmltext'.
    # An aliased import like 'import htmltext as h' does NOT make
    # the bare name 'htmltext' available for type annotations.
    for node in tree.body:
        if isinstance(node, ast.ImportFrom) and node.module == 'quixote.html':
            if any(
                alias.name == 'htmltext' and alias.asname is None
                for alias in node.names
            ):
                return source

    # Find insertion point: after the last top-level import
    # (or after module docstring if no imports exist)
    insert_lineno = 0  # 0-based line index for insertion
    seen_docstring = False
    for node in tree.body:
        if (
            not seen_docstring
            and isinstance(node, ast.Expr)
            and isinstance(node.value, ast.Constant)
            and isinstance(node.value.value, str)
        ):
            seen_docstring = True
            insert_lineno = node.end_lineno or node.lineno
            continue
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            insert_lineno = node.end_lineno or node.lineno
            continue
        break

    lines = source.split('\n')
    lines.insert(insert_lineno, 'from quixote.html import htmltext')
    return '\n'.join(lines)


def translate(fn: str, verbose: bool = False) -> tuple[str, int]:
    """Process a file, returning (source, n_fixed)."""
    with open(fn, encoding='utf-8') as fp:
        source = fp.read()

    try:
        tree = ast.parse(source, filename=fn)
    except SyntaxError as exc:
        print(f'  SyntaxError: {exc}', file=sys.stderr)
        return source, 0

    funcs = find_ptl_html_functions(tree)
    if not funcs:
        if verbose:
            sys.stdout.write(source)
        return source, 0

    lines = source.splitlines(keepends=True)
    n_fixed = 0

    # Process bottom-up to preserve line offsets
    for func in sorted(funcs, key=lambda f: -f.lineno):
        if fix_return_type(lines, func):
            n_fixed += 1

    result = ''.join(lines)

    # Add htmltext import if we made changes
    if n_fixed > 0:
        result = add_htmltext_import(result, tree)

    if verbose:
        sys.stdout.write(result)
    return result, n_fixed


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(
        description='Add -> htmltext return type to @ptl_html functions'
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
        help='re-write files in-place',
    )
    parser.add_argument('files', nargs='*')
    args = parser.parse_args()
    if not args.write:
        args.verbose = True

    if not args.files:
        parser.error('no input files')

    total_fixed = 0
    for fn in args.files:
        header = '## %s ' % fn
        header = header.ljust(78, '#')
        print(header, file=sys.stderr)
        src, n_fixed = translate(fn, verbose=args.verbose)
        print(f'  {n_fixed} fixed', file=sys.stderr)
        total_fixed += n_fixed
        if args.write:
            if n_fixed > 0:
                os.rename(fn, fn + '~')
                with open(fn, 'w', encoding='utf-8') as fp:
                    fp.write(src)

    if len(args.files) > 1:
        print(f'\nTotal: {total_fixed} fixed', file=sys.stderr)


if __name__ == '__main__':
    main()
