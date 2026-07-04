"""Root conftest: makes custom_components importable in tests."""

import sys


def pytest_configure(config) -> None:
    """Keep sockets usable when developing on Windows.

    pytest-homeassistant-custom-component calls disable_socket with
    allow_unix_socket=True. Windows has no AF_UNIX socketpair, so the
    Proactor event loop's self-pipe would be blocked and every test errors
    during event loop creation. CI (Linux) is unaffected.
    """
    if sys.platform == "win32":
        import pytest_socket

        pytest_socket.disable_socket = lambda allow_unix_socket=False: None
