import quixote.html

try:
    import qpy
except ImportError:
    qpy = None

if qpy:

    def setup() -> None:
        quixote.html.use_qpy()

    def test() -> None:
        import quixote

        assert quixote.html.htmltext == qpy.h8

    def teardown() -> None:
        quixote.html.cleanup_qpy()
