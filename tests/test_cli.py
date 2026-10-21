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


def test_cli_recovery_scenario(tmp_path):
    report = tmp_path / "recovery.json"
    finished = subprocess.run(
        [sys.executable, "-m", "hil_automation.cli",
         str(ROOT / "scenarios" / "recovery.yaml"), "--report", str(report)],
        capture_output=True, text=True,
    )
    assert finished.returncode == 0, finished.stderr
    data = json.loads(report.read_text())
    assert data["suite"] == "simulated-recovery"
    assert (data["passed"], data["failed"]) == (3, 0)
    assert [case["name"] for case in data["results"]] == [
        "cool_after_thermal_load", "reconnect_after_link_interruption",
        "fresh_case_starts_healthy",
    ]
    assert all(case["status"] == "passed" for case in data["results"])
    assert all(case["details"] == "All steps passed" for case in data["results"])
    assert all(case["duration_ms"] >= 0 for case in data["results"])
    assert data["started_at"]
    assert "3 passed, 0 failed" in finished.stdout


def test_cli_fault_scenario(tmp_path):
    report = tmp_path / "faults.json"
    finished = subprocess.run(
        [sys.executable, "-m", "hil_automation.cli",
         str(ROOT / "scenarios" / "faults.yaml"), "--report", str(report)],
        capture_output=True, text=True,
    )
    assert finished.returncode == 1, finished.stderr
    data = json.loads(report.read_text())
    assert data["suite"] == "simulated-faults"
    assert (data["passed"], data["failed"]) == (0, 2)
    assert [case["name"] for case in data["results"]] == [
        "thermal_overload", "lost_device_connection",
    ]
    assert all(case["status"] == "failed" for case in data["results"])
    assert data["results"][0]["details"] == "Step 3: Temperature 95.0 °C is not below limit 75.0 °C"
    assert data["results"][1]["details"] == "Step 3: Device heartbeat not detected; expected an active connection"
    assert "0 passed, 2 failed" in finished.stdout
