from pathlib import Path

from teams_archive.capture.browser import chrome_executable
from teams_archive.config import LOOPBACK_HOST


def test_server_is_loopback_only() -> None:
    assert LOOPBACK_HOST == "127.0.0.1"


def test_runtime_has_no_graph_or_msal_dependency() -> None:
    pyproject = Path("pyproject.toml").read_text(encoding="utf-8").lower()
    assert "msal" not in pyproject
    assert "google-api-python-client" not in pyproject
    assert not Path("backend/teams_archive/connectors/microsoft.py").exists()


def test_chrome_is_detectable_on_linux_pilot_host() -> None:
    assert chrome_executable()
