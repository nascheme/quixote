import quixote.html

try:
    import qpy
except ImportError:
    qpy = None

if qpy:

    def setup():
        quixote.html.use_qpy()

    def test():
        import quixote

        assert quixote.html.htmltext == qpy.h8

    def teardown():
        quixote.html.cleanup_qpy()
