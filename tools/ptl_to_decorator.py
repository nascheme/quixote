#!/usr/bin/env python3
# vim: set ai tw=74 sts=4 sw=4 et:
"""
Convert .ptl files to use decorator syntax for templates and F prefix for
h-strings.

The code transforms are as follows:

    def func [html] () -> @ptl_html
                          def func()

    def func [plain] () -> @ptl_plain
                           def func()

    h'hello' -> F'hello'

Note that this tool does not add the import of the decorator.  E.g.

    from quixote.ptl import ptl_html

"""

import sys
import os
import tokenize


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
                template_func = 'ptl_' + template_type
                t = tokens[i + 1]
                line, col = tok.start
                # delete extra tokens from [html] or [plain]
                tokens[i + 1 : i + 4] = []
                end = (t.end[0], t.end[1] + len(template_type) + 4)
                start = (t.start[0], tok.end[1] + 1)
                indent = ' ' * tok.start[1]
                # putting newline in tok.string is ugly but it works
                s = '@' + template_func + '\n' + indent + tok.string
                tokens[i] = tokenize.TokenInfo(
                    tok.type, s, tok.start, tok.end, tok.line
                )
                tokens[i + 1] = tokenize.TokenInfo(
                    t.type, t.string, start, end, t.line
                )
                # print('tokens', tokens[i-1:i+3])
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


def translate(fn, verbose=False):
    with open(fn, 'rb') as fp:
        tokens = list(tokenize.tokenize(fp.readline))
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
    parser.add_argument('files', nargs='+')
    args = parser.parse_args()
    if not args.write:
        args.verbose = True
    for fn in args.files:
        header = '## %s ' % fn
        header = header.ljust(78, '#')
        print(header, file=sys.stderr)
        encoding, src = translate(fn, verbose=args.verbose)
        if args.write:
            os.rename(fn, fn + '~')
            with open(fn, 'w', encoding=encoding) as fp:
                fp.write(src)


if __name__ == '__main__':
    main()
