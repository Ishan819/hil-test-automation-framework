import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_cli_generates_report(tmp_path):
    report = tmp_path / "result.json"
    command = [sys.executable, "-m", "hil_automation.cli", str(ROOT / "scenarios" / "smoke.yaml"), "--report", str(report)]
    finished = subprocess.run(command, capture_output=True, text=True)
    assert finished.returncode == 0, finished.stderr
    data = json.loads(report.read_text())
    assert data["passed"] == 3
    assert data["failed"] == 0


def test_cli_fails_on_failed_cases(tmp_path):
    report = tmp_path / "failure.json"
    command = [sys.executable, "-m", "hil_automation.cli", str(ROOT / "scenarios" / "failure_demo.yaml"), "--report", str(report)]
    finished = subprocess.run(command, capture_output=True, text=True)
    assert finished.returncode == 1
    assert json.loads(report.read_text())["failed"] == 2
