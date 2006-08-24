#!/usr/bin/env python

# Setup script for Quixote

import sys
import os
from distutils import core
from distutils.extension import Extension
from ptl.qx_distutils import qx_build_py

VERSION = '2.5a1'

# Ensure that version number is correct.
def _check_version_numbers():
    from __init__ import __version__
    import re
    assert VERSION == __version__
    PAT = re.compile(r'^%s\b' % re.escape(VERSION), re.MULTILINE)
    if not PAT.search(open("CHANGES.txt").read(400)):
        raise AssertionError("version number mismatch in CHANGES.txt")

if 'sdist' in sys.argv[1:]:
    _check_version_numbers()

# a fast htmltext type
htmltext = Extension(name="quixote.html._c_htmltext",
                     sources=["html/_c_htmltext.c"])

# faster import hook for PTL modules
cimport = Extension(name="quixote.ptl.cimport",
                    sources=["ptl/cimport.c"])

kw = {'name': "Quixote",
      'version': VERSION,
      'description': "A highly Pythonic Web application framework",
      'author': "MEMS Exchange",
      'author_email': "quixote@mems-exchange.org",
      'url': "http://www.quixote.ca/",
      'license': "DFSG approved open source (see LICENSE.txt)",

      'package_dir': {'quixote': os.curdir},
      'packages': ['quixote',  'quixote.demo', 'quixote.form',
                   'quixote.html', 'quixote.ptl',
                   'quixote.server'],

      'ext_modules': [],

      'cmdclass': {'build_py': qx_build_py},
     }


build_extensions = sys.platform != 'win32'

if build_extensions:
    # The _c_htmltext module requires Python 2.2 features.
    if sys.hexversion >= 0x20200a1:
        kw['ext_modules'].append(htmltext)
    kw['ext_modules'].append(cimport)

# If we're running Python 2.3, add extra information
if hasattr(core, 'setup_keywords'):
    if 'classifiers' in core.setup_keywords:
        kw['classifiers'] = ['Development Status :: 5 - Production/Stable',
          'Environment :: Web Environment',
          'License :: DFSG approved',
          'Intended Audience :: Developers',
          'Operating System :: Unix',
          'Operating System :: Microsoft :: Windows',
          'Operating System :: MacOS :: MacOS X',
          'Topic :: Internet :: WWW/HTTP :: Dynamic Content',
          ]
    if 'download_url' in core.setup_keywords:
        kw['download_url'] = ('http://quixote.python.ca/releases/'
                              'Quixote-%s.tar.gz' % kw['version'])

core.setup(**kw)
