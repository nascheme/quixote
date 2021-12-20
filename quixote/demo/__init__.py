from quixote import enable_ptl
from quixote.publish import Publisher

enable_ptl()


def create_publisher():
    from quixote.demo.root import RootDirectory

    return Publisher(RootDirectory(), display_exceptions='plain')
