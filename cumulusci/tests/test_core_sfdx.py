import sarge
import pytest

from cumulusci.core.exceptions import SfdxOrgException
from cumulusci.core import sfdx as sfdx_module


class _FakeCommand:
    def __init__(self, command, **kwargs):
        self.command = command
        self.kwargs = kwargs
        self.returncode = 0

    def run(self):
        return None


def test_sfdx_coerces_args_to_strings(monkeypatch):
    captured = {}

    def fake_command(command, **kwargs):
        captured["command"] = command
        captured["kwargs"] = kwargs
        return _FakeCommand(command, **kwargs)

    monkeypatch.setattr(sarge, "Command", fake_command)

    sfdx_module.sfdx("clariti org checkout", args=[1, "--flag"], capture_output=False)

    assert captured["command"].startswith("sf clariti org checkout ")
    assert " 1 " in captured["command"] or captured["command"].endswith(" 1")
    assert captured["kwargs"]["shell"] is True


def test_sfdx_raises_on_none_arg(monkeypatch):
    monkeypatch.setattr(sarge, "Command", _FakeCommand)

    with pytest.raises(SfdxOrgException):
        sfdx_module.sfdx("org display", args=["--json", None], capture_output=False)
