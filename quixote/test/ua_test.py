#!/usr/bin/env python

# Test Quixote's ability to parse the "User-Agent" header, ie.
# the 'guess_browser_version()' method of HTTPRequest.
#
# Reads User-Agent strings on stdin, and writes Quixote's interpretation
# of each on stdout.  This is *not* an automated test!

import sys, os
from copy import copy
from quixote.http_request import HTTPRequest

if __name__ == '__main__':
    env = copy(os.environ)
    file = sys.stdin
    while 1:
        line = file.readline()
        if not line:
            break
        if line[-1] == "\n":
            line = line[:-1]

        env["HTTP_USER_AGENT"] = line
        req = HTTPRequest(None, env)
        (name, version) = req.guess_browser_version()
        if name is None:
            print("%s -> ???" % line)
        else:
            print("%s -> (%s, %s)" % (line, name, version))
