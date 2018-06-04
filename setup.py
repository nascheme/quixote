#!/usr/bin/env python3
#try:
#    from setuptools import setup
#except ImportError:
#    print('(WARNING: importing distutils, not setuptools!)')
#    from distutils.core import setup

# Setup script for Quixote

import sys

if sys.version_info < (3,6,0):
    raise SystemExit("You need python 3.6.0 or later to run this script")

from distutils import core
from distutils.extension import Extension
from quixote.ptl.qx_distutils import qx_build_py
from quixote import __version__

# a fast htmltext type
htmltext = Extension(name="quixote.html._c_htmltext",
                     sources=["quixote/html/_c_htmltext.c"])

kw = {'name': "Quixote",
      'version': __version__,
      'description': "A small and flexible Python Web application framework",
      'author': "The Quixote developers",
      'author_email': "webmaster@quixote.ca",
      'url': "http://www.quixote.ca/",
      'license': "DFSG approved (see LICENSE.txt)",

      'package_dir': {'quixote': 'quixote'},
      'packages': ['quixote',  'quixote.demo', 'quixote.form',
                   'quixote.html', 'quixote.ptl',
                   'quixote.server'],

      'ext_modules': [],

      'cmdclass': {'build_py': qx_build_py},

#      'test_suite' : 'nose.collector'
     }


build_extensions = sys.platform != 'win32'

if build_extensions:
    kw['ext_modules'].append(htmltext)

# If we're running Python 2.3, add extra information
if hasattr(core, 'setup_keywords'):
    if 'classifiers' in core.setup_keywords:
        kw['classifiers'] = [
          'Development Status :: 5 - Production/Stable',
          'Environment :: Web Environment',
          'License :: DFSG approved',
          'Intended Audience :: Developers',
          'Operating System :: Unix',
          'Operating System :: Microsoft :: Windows',
          'Operating System :: MacOS :: MacOS X',
          'Topic :: Internet :: WWW/HTTP :: Dynamic Content',
          'Programming Language :: Python :: 3 :: Only',
          ]
    if 'download_url' in core.setup_keywords:
        kw['download_url'] = ('http://quixote.ca/releases/'
                              'Quixote-%s.tar.gz' % kw['version'])
    if 'url' in core.setup_keywords:
        kw['url'] = 'http://www.quixote.ca/'
    if 'platforms' in core.setup_keywords:
        kw['platforms'] = 'Most'

core.setup(**kw)
