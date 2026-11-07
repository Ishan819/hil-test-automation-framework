import sys

import pytest

from hil_automation import cli, doctor


@pytest.mark.parametrize("required, available, code, status", [
    (True, True, 0, "PASS"), (True, False, 2, "FAIL"),
    (False, False, 0, "OPTIONAL MISSING"),
])
def test_doctor_output_and_exit_code(monkeypatch, capsys, required, available, code, status):
    monkeypatch.setattr(doctor, "check_environment", lambda: [doctor.Check("component", required, available, "diagnostic")])
    monkeypatch.setattr(sys, "argv", ["hil-run", "--doctor"])
    assert cli.main() == code
    captured = capsys.readouterr()
    assert captured.out == f"[{status}] component: diagnostic\n"
    assert captured.err == ""
