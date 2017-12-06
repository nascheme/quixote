#!/usr/bin/env python3
# vim: set ai tw=74 sts=4 sw=4 et:
#
# Convert .ptl files to new h-string format.
# Use -w argument to write files in-place.
#
# This tool seems to work well but there are probably some weird syntax that
# will confuse it.  You will need to examine and test your code after doing
# the conversion.

import sys
import os
import tokenize
import ast
import re

def translate_hstrings(tokens):
    i = 0
    context = [False]
    html_def = False # True if upcoming indent enters html template
    # test if string contains markup characters and needs escaping.  We
    # also include strings that contain % format characters (otherwise str
    # formatting would convert htmltext to str).  If the string doesn't
    # contain any of these characters, we will leave it as an ordinary
    # string.
    need_escape = re.compile(r'[&<>"%]').search
    # test if a string appears on the same line as a .join call, if so,
    # change it to an h-string since str.join doesn't handle htmltext
    # strings.
    is_join = re.compile(r'["\']\.join').search
    while i < len(tokens):
        tok = tokens[i]
        if tok.type == tokenize.NAME and tok.string == 'def':
            if (tokens[i+2][:2] == (tokenize.OP, '[') and
                tokens[i+3][1] == 'html' and
                tokens[i+4][:2] == (tokenize.OP, ']')):
                html_def = True
            else:
                html_def = False
        elif tok.type == tokenize.INDENT:
            if html_def:
                context.append(True)
                html_def = False
            else:
                context.append(context[-1])
        elif tok.type == tokenize.DEDENT:
            context.pop()
        elif tok.type == tokenize.STRING and context[-1]:
            # found literal string inside html template
            str_tok = list(tokens[i])
            # prefix string with marker
            s = str_tok[1]
            if s[:1] == 'f':
                # we could support this, just gets more complicated
                raise RuntimeError('f-strings in PTL source not supported '
                                   'by conversion. %r' % tok.line)
            if s[:1] not in {'"', "'", 'u'}:
                raise RuntimeError('bad string in html template %r' % s)
            if need_escape(ast.literal_eval(s)) or is_join(tok.line):
                # we are creating h-string
                if '{' in s:
                    # escape f-string chars
                    s = s.replace('{', '{{')
                    s = s.replace('}', '}}')
                str_tok[1] = 'h' + s
                tokens[i] = tokenize.TokenInfo(*str_tok)
        i += 1


def translate(fn, verbose=False):
    with open(fn, 'rb') as fp:
        tokens = list(tokenize.tokenize(fp.readline))
    translate_hstrings(tokens)
    ut = tokenize.Untokenizer()
    src = ut.untokenize(tokens)
    if verbose:
        sys.stdout.write(src)
    return ut.encoding, src


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('-v', '--verbose', default=False,
                        action='store_true',
                        help="write source to stdout")
    parser.add_argument('--write', '-w', default=False,
                        action="store_true",
                        help="re-write files")
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
