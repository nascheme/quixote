These are tests for developers of Quixote 2.x.

To run them, you will need to install 'nose' and 'twill':

   easy_install nose

   easy_install http://darcs.idyll.org/~t/projects/twill-latest.tar.gz

Then, in the Quixote directory, run 'python setup.py build'.  Put the
resulting build library in your PYTHONPATH, e.g.

   export PYTHONPATH=/path/to/quixote/build/lib.linux-i686-2.4/

Finally, run 'nosetests' in the top-level Quixote directory, i.e. the directory
containing CHANGES.txt.
