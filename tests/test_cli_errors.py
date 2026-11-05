"""Regression checks for malformed inputs at the public CLI boundary."""
import sys

import pytest

from hil_automation import cli


@pytest.mark.parametrize("plan", [False, True])
@pytest.mark.parametrize("content", [b'private-token: [SECRET_VALUE\n', b'\xff'])
def test_invalid_yaml_has_safe_diagnostic(tmp_path, monkeypatch, capsys, plan, content):
    source = tmp_path / "invalid.yaml"
    source.write_bytes(content)
    monkeypatch.setattr(sys, "argv", ["hil-run", *(["--plan"] if plan else []), str(source)])
    assert cli.main() == 2
    captured = capsys.readouterr()
    assert "Invalid" in captured.err and "YAML" in captured.err
    assert "SECRET_VALUE" not in captured.err
    assert "Traceback" not in captured.err and not captured.out
    if content.startswith(b'private'):
        assert "line 2, column 1" in captured.err


@pytest.mark.parametrize("action", ["[]", "{}", "null"])
def test_non_string_action_returns_configuration_error(tmp_path, monkeypatch, capsys, action):
    source = tmp_path / "invalid.yaml"
    source.write_text(f"suite: invalid\nbench: {{type: simulated}}\ntests:\n"
                      f"  - name: invalid\n    steps: [{{action: {action}}}]\n")
    monkeypatch.setattr(sys, "argv", ["hil-run", str(source)])
    assert cli.main() == 2
    captured = capsys.readouterr()
    assert "Unknown action" in captured.err and not captured.out
