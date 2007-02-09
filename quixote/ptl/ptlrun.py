#!/usr/bin/env python
import sys
from quixote.ptl.ptl_compile import compile_template
if __name__ == '__main__':
    exec compile_template(open(sys.argv[1]), sys.argv[1])

