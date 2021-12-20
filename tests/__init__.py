import qx_testlib
import qx_testserver
import twill

url = None


def setup(package):
    qx_testlib.cd_testdir()
    package.url = qx_testlib.run_server(qx_testserver.create_publisher)


def teardown(package):
    qx_testlib.kill_server()
    qx_testlib.pop_testdir()


def test():
    twill.commands.go(url)
    twill.commands.find('hello, world')
