#!/usr/bin/env python3
# vim: set ai tw=74 sts=4 sw=4 et:
"""
Convert uppercase F-strings in .ptl files to H(t"...") calls.
Use -w argument to write files in-place.

Uppercase F"..." is Quixote's PTL htmltext literal syntax.
This converts them to H(t"...") where H is imported as
`from quixote.html import htmlformat as H`.

The t-string (PEP 750) preserves the original interpolation
syntax and H() converts the Template to htmltext.
"""

import sys
import os
import token
import tokenize
import io
import re
from dataclasses import dataclass


@dataclass
class FStringLoc:
    """Location of one uppercase F-string."""

    start_offset: int  # byte offset of 'F' prefix
    end_offset: int  # byte offset after closing quote
    adjacent_next: bool = (
        False  # followed by another F-string (implicit concat)
    )


def build_line_offsets(source: bytes) -> list[int]:
    """Build a map from 1-based line number to byte offset of line start."""
    offsets = [0, 0]  # index 0 unused, index 1 = offset of line 1
    for i, b in enumerate(source):
        if b == ord('\n'):
            offsets.append(i + 1)
    return offsets


def pos_to_offset(line_offsets: list[int], line: int, col: int) -> int:
    """Convert (line, col) token position to byte offset."""
    return line_offsets[line] + col


def _skip_fstring(tokens: list[tokenize.TokenInfo], start: int) -> int:
    """Return index after the matching FSTRING_END for tokens[start]."""
    depth = 0
    i = start
    while i < len(tokens):
        if tokens[i].type == token.FSTRING_START:
            depth += 1
        elif tokens[i].type == token.FSTRING_END:
            depth -= 1
            if depth == 0:
                return i + 1
        i += 1
    return i


def _is_adjacent_fstring(
    tokens: list[tokenize.TokenInfo], fstring_end_idx: int
) -> bool:
    """Check if another uppercase F-string follows (implicit concatenation).

    Only returns True if the next F-string is part of the same expression
    (i.e., only NL tokens between them, not NEWLINE which indicates a
    logical line end / separate statement).
    """
    j = fstring_end_idx + 1
    while j < len(tokens):
        t = tokens[j]
        if t.type == token.NEWLINE:
            return False  # logical line end — separate statement
        if t.type in (
            token.NL,
            token.COMMENT,
            token.INDENT,
            token.DEDENT,
        ):
            j += 1
            continue
        return t.type == token.FSTRING_START and t.string.startswith('F')
    return False


def collect_fstrings(
    tokens: list[tokenize.TokenInfo],
    line_offsets: list[int],
) -> list[FStringLoc]:
    """Walk token stream and collect uppercase F-string locations."""
    results: list[FStringLoc] = []
    i = 0
    while i < len(tokens):
        tok = tokens[i]
        if tok.type == token.FSTRING_START and tok.string.startswith('F'):
            start_offset = pos_to_offset(
                line_offsets, tok.start[0], tok.start[1]
            )
            end_idx = _skip_fstring(tokens, i) - 1  # FSTRING_END index
            end_tok = tokens[end_idx]
            end_offset = pos_to_offset(
                line_offsets, end_tok.end[0], end_tok.end[1]
            )
            loc = FStringLoc(
                start_offset=start_offset,
                end_offset=end_offset,
                adjacent_next=_is_adjacent_fstring(tokens, end_idx),
            )
            results.append(loc)
            i = end_idx + 1
            continue
        i += 1
    return results


def build_replacement(loc: FStringLoc, source: bytes) -> str:
    """Build replacement text: H(t"...") from F"..."."""
    original = source[loc.start_offset : loc.end_offset].decode('utf-8')
    # Replace leading F with t, wrap in H()
    tstring = 't' + original[1:]
    suffix = ' +' if loc.adjacent_next else ''
    return f'H({tstring}){suffix}'


def add_import(source_text: str) -> str:
    """Add H import to source if needed.

    Add `from quixote.html import htmlformat as H` after
    the last top-level `from quixote` import, or after the import block.
    """
    lines = source_text.split('\n')

    # Find last top-level `from quixote` import line
    last_quixote_import = -1
    quixote_import_re = re.compile(r'^from\s+quixote\b')
    for i, line in enumerate(lines):
        if quixote_import_re.match(line):
            last_quixote_import = i

    if last_quixote_import >= 0:
        lines.insert(
            last_quixote_import + 1,
            'from quixote.html import htmlformat as H',
        )
        return '\n'.join(lines)

    # Find end of import block
    last_import = -1
    import_re = re.compile(r'^\s*(import|from)\s+')
    for i, line in enumerate(lines):
        if import_re.match(line):
            last_import = i

    if last_import >= 0:
        lines.insert(
            last_import + 1, 'from quixote.html import htmlformat as H'
        )
    else:
        # No imports at all, add at top (after shebang/encoding)
        insert_at = 0
        for i, line in enumerate(lines):
            if line.startswith('#') or line.strip() == '':
                insert_at = i + 1
            else:
                break
        lines.insert(insert_at, 'from quixote.html import htmlformat as H')

    return '\n'.join(lines)


def translate(fn: str, verbose: bool = False) -> tuple[str, str, int]:
    """Translate a file, returning (encoding, source, n_converted)."""
    with open(fn, 'rb') as fp:
        source = fp.read()

    # Tokenize
    tokens = list(tokenize.tokenize(io.BytesIO(source).readline))
    encoding = 'utf-8'
    if tokens and tokens[0].type == token.ENCODING:
        encoding = tokens[0].string

    line_offsets = build_line_offsets(source)

    # Collect F-string locations
    fstrings = collect_fstrings(tokens, line_offsets)

    if not fstrings:
        src = source.decode(encoding)
        if verbose:
            sys.stdout.write(src)
        return encoding, src, 0

    # Build and apply replacements (end-to-start to preserve offsets)
    result = source
    n_converted = 0
    for loc in reversed(fstrings):
        repl = build_replacement(loc, source)
        repl_bytes = repl.encode(encoding)
        result = (
            result[: loc.start_offset] + repl_bytes + result[loc.end_offset :]
        )
        n_converted += 1

    src = result.decode(encoding)

    # Add import
    src = add_import(src)

    if verbose:
        sys.stdout.write(src)

    return encoding, src, n_converted


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(
        description='Convert uppercase F-strings to H(t"...") calls'
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
        encoding, src, n_converted = translate(fn, verbose=args.verbose)
        print(f'  {n_converted} converted', file=sys.stderr)
        total_converted += n_converted
        if args.write:
            os.rename(fn, fn + '~')
            with open(fn, 'w', encoding=encoding) as fp:
                fp.write(src)
    if len(args.files) > 1:
        print(f'\nTotal: {total_converted} converted', file=sys.stderr)


if __name__ == '__main__':
    main()
