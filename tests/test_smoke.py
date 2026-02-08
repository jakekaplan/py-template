from py_template import ping


def test_ping() -> None:
    assert ping() == "pong"
