#!/usr/bin/env python3
# vim: set ai tw=74 sts=4 sw=4 et:
"""
Convert .ptl files to valid .py files.  PTL syntax is turned into
compatible Python syntax.  This is useful so you can run linters (like
flake8) or code formaters (like black) on it.

Use --reverse option to convert back.  Use -w argument to write files
in-place.

The code transforms are as follows:

    def func [html] () -> def _q_html_func()

    def func [plain] () -> def _q_plain_func()

    h'hello' -> F'hello'

"""

import sys
import os
import tokenize

HTML_PREFIX = '_q_html_'
PLAIN_PREFIX = '_q_plain_'


def translate_ptl(tokens):
    i = 0
    while i < len(tokens):
        tok = tokens[i]
        if tok.type == tokenize.NAME and tok.string == 'def':
            if (
                tokens[i + 2][:2] == (tokenize.OP, '[')
                and tokens[i + 3][1] in {'html', 'plain'}
                and tokens[i + 4][:2] == (tokenize.OP, ']')
            ):
                template_type = tokens[i + 3][1]
                t = tokens[i + 1]
                tokens[i + 1 : i + 4] = []
                end = t.end
                if str(template_type) == 'plain':
                    prefix = PLAIN_PREFIX
                else:
                    prefix = HTML_PREFIX
                tokens[i + 1] = tokenize.TokenInfo(
                    t.type,
                    prefix + t.string,
                    t.start,
                    (end[0], end[1] + len(prefix)),
                    t.line,
                )
        elif tok.type == tokenize.NAME and tok.string == 'h':
            try:
                str_tok = tokens[i + 1]
                if str_tok.type == tokenize.STRING:
                    t = tokens[i]
                    tokens[i] = tokenize.TokenInfo(
                        t.type, 'F', t.start, t.end, t.line
                    )
            except IndexError:
                pass
        i += 1


def translate_py(tokens):
    i = 0
    while i < len(tokens):
        tok = tokens[i]
        if tok.type == tokenize.NAME and tok.string == 'def':
            t = tokens[i + 1]
            if t.type == tokenize.NAME:
                if t.string.startswith(HTML_PREFIX):
                    template_type = 'html'
                    prefix = HTML_PREFIX
                elif t.string.startswith(PLAIN_PREFIX):
                    template_type = 'plain'
                    prefix = PLAIN_PREFIX
                else:
                    template_type = ''
                if template_type:
                    func_name = t.string[len(prefix) :]
                    func_name += ' [' + template_type + '] '
                    tokens[i + 1] = tokenize.TokenInfo(
                        t.type, func_name, t.start, t.end, t.line
                    )
        elif tok.type == tokenize.STRING and tok.string[0] == 'F':
            tokens[i] = tokenize.TokenInfo(
                tok.type, 'h' + tok.string[1:], tok.start, tok.end, tok.line
            )
        i += 1


def translate(fn, verbose=False, reverse=False):
    with open(fn, 'rb') as fp:
        tokens = list(tokenize.tokenize(fp.readline))
    if reverse:
        translate_py(tokens)
    else:
        translate_ptl(tokens)
    ut = tokenize.Untokenizer()
    src = ut.untokenize(tokens)
    if verbose:
        sys.stdout.write(src)
    return ut.encoding, src


def main():
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument(
        '-v',
        '--verbose',
        default=False,
        action='store_true',
        help="write source to stdout",
    )
    parser.add_argument(
        '--write',
        '-w',
        default=False,
        action="store_true",
        help="re-write files",
    )
    parser.add_argument(
        '--reverse',
        '-r',
        default=False,
        action="store_true",
        help="Reverse operation (.py to .ptl)",
    )
    parser.add_argument('files', nargs='+')
    args = parser.parse_args()
    if not args.write:
        args.verbose = True
    for fn in args.files:
        header = '## %s ' % fn
        header = header.ljust(78, '#')
        print(header, file=sys.stderr)
        encoding, src = translate(
            fn, verbose=args.verbose, reverse=args.reverse
        )
        if args.write:
            os.rename(fn, fn + '~')
            with open(fn, 'w', encoding=encoding) as fp:
                fp.write(src)


if __name__ == '__main__':
    main()
