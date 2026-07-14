from typing import Any

import qx_testlib
import qx_testserver
import twill

url: str | None = None


def setup(package: Any) -> None:
    qx_testlib.cd_testdir()
    package.url = qx_testlib.run_server(qx_testserver.create_publisher)


def teardown(package: Any) -> None:
    qx_testlib.kill_server()
    qx_testlib.pop_testdir()


def test() -> None:
    twill.commands.go(url)
    twill.commands.find('hello, world')
