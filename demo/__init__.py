"""$URL: svn+ssh://svn.mems-exchange.org/repos/trunk/quixote/demo/__init__.py $
$Id: __init__.py 25575 2004-11-11 16:56:44Z nascheme $
"""
from quixote import enable_ptl
from quixote.publish import Publisher
enable_ptl()

def create_publisher():
    from quixote.demo.root import RootDirectory
    return Publisher(RootDirectory(), display_exceptions='plain')
