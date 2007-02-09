import quixote, qx_testserver
from wsgiref.simple_server import make_server

qx_testserver.create_publisher()
wsgi_app = quixote.get_wsgi_app()

httpd = make_server('', 8000, wsgi_app)
httpd.serve_forever()
