#!/usr/bin/env python3

# Setup script for Quixote

import sys

if sys.version_info < (3,6,0):
    raise SystemExit("You need python 3.6.0 or later to run this script")

import sys
from setuptools import setup, Extension
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

      #'cmdclass': {'build_py': qx_build_py},

     }


build_extensions = sys.platform != 'win32'

if build_extensions:
    kw['ext_modules'].append(htmltext)

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
kw['download_url'] = ('http://quixote.ca/releases/'
                      'Quixote-%s.tar.gz' % kw['version'])
kw['url'] = 'http://www.quixote.ca/'
kw['platforms'] = 'Most'

setup(**kw)
