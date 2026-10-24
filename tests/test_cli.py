import json
import subprocess
import sys
from pathlib import Path

import pytest


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


def test_cli_lists_cases_without_writing_report(tmp_path):
    report = tmp_path / "listing.json"
    finished = subprocess.run(
        [sys.executable, "-m", "hil_automation.cli",
         str(ROOT / "scenarios" / "faults.yaml"), "--list-tests",
         "--report", str(report)],
        capture_output=True, text=True,
    )
    assert finished.returncode == 0, finished.stderr
    assert finished.stdout.splitlines() == [
        "Suite: simulated-faults", "  thermal_overload", "  lost_device_connection",
    ]
    assert finished.stderr == ""
    assert not report.exists()


def test_listing_does_not_execute_suite(monkeypatch, capsys):
    from hil_automation import cli

    def unexpected_run(suite):
        raise AssertionError("Listing must not execute cases")

    monkeypatch.setattr(cli, "run_suite", unexpected_run)
    monkeypatch.setattr(sys, "argv", [
        "hil-run", str(ROOT / "scenarios" / "smoke.yaml"), "--list-tests",
    ])
    assert cli.main() == 0
    assert "power_rail_reaches_five_volts" in capsys.readouterr().out


def test_cli_runs_only_selected_case_with_initial_bench_state(tmp_path):
    config = tmp_path / "selection.yaml"
    config.write_text("""suite: selection
bench: {type: simulated, initial_voltage: 3.3, temperature_c: 35, connected: true}
tests:
  - name: mutate-and-fail
    steps:
      - {action: set_voltage, value: 12}
      - {action: set_temperature, value: 95}
      - {action: set_connection, connected: false}
      - {action: expect_heartbeat}
  - name: initial-state
    steps:
      - {action: expect_voltage, value: 3.3, tolerance: 0}
      - {action: expect_temperature_below, limit_c: 36}
      - {action: expect_heartbeat}
""", encoding="utf-8")
    report = tmp_path / "selected.json"
    finished = subprocess.run(
        [sys.executable, "-m", "hil_automation.cli", str(config),
         "--case", "initial-state", "--report", str(report)],
        capture_output=True, text=True,
    )
    assert finished.returncode == 0, finished.stderr
    data = json.loads(report.read_text())
    assert data["suite"] == "selection"
    assert (data["passed"], data["failed"]) == (1, 0)
    assert [case["name"] for case in data["results"]] == ["initial-state"]
    assert "mutate-and-fail" not in finished.stdout


def test_cli_rejects_listing_and_execution_together(tmp_path):
    report = tmp_path / "conflict.json"
    finished = subprocess.run(
        [sys.executable, "-m", "hil_automation.cli",
         str(ROOT / "scenarios" / "smoke.yaml"), "--list-tests",
         "--case", "device_responds_to_heartbeat", "--report", str(report)],
        capture_output=True, text=True,
    )
    assert finished.returncode == 2
    assert "not allowed with argument" in finished.stderr
    assert not report.exists()


def test_unknown_case_lists_available_names_and_preserves_report(tmp_path):
    report = tmp_path / "existing.json"
    report.write_text("existing report", encoding="utf-8")
    finished = subprocess.run(
        [sys.executable, "-m", "hil_automation.cli",
         str(ROOT / "scenarios" / "faults.yaml"), "--case", "missing",
         "--report", str(report)],
        capture_output=True, text=True,
    )
    assert finished.returncode == 2
    assert finished.stdout == ""
    assert finished.stderr == (
        "Error: Unknown test case: 'missing'. Available cases: "
        "thermal_overload, lost_device_connection\n"
    )
    assert report.read_text() == "existing report"


def test_unknown_case_does_not_execute_or_create_report(monkeypatch, capsys, tmp_path):
    from hil_automation import cli

    def unexpected_run(suite):
        raise AssertionError("Unknown names must be rejected before execution")

    report = tmp_path / "unused" / "report.json"
    monkeypatch.setattr(cli, "run_suite", unexpected_run)
    monkeypatch.setattr(sys, "argv", [
        "hil-run", str(ROOT / "scenarios" / "smoke.yaml"),
        "--case", "Device_responds_to_heartbeat", "--report", str(report),
    ])
    assert cli.main() == 2
    assert "device_responds_to_heartbeat" in capsys.readouterr().err
    assert not report.parent.exists()


@pytest.mark.parametrize("scenario, name, status, exit_code, details", [
    ("recovery.yaml", "reconnect_after_link_interruption", "passed", 0, "All steps passed"),
    ("faults.yaml", "thermal_overload", "failed", 1,
     "Step 3: Temperature 95.0 °C is not below limit 75.0 °C"),
    ("faults.yaml", "lost_device_connection", "failed", 1,
     "Step 3: Device heartbeat not detected; expected an active connection"),
])
def test_filtered_cli_report_compatibility(tmp_path, scenario, name, status, exit_code, details):
    report = tmp_path / "nested" / "filtered.json"
    finished = subprocess.run(
        [sys.executable, "-m", "hil_automation.cli",
         str(ROOT / "scenarios" / scenario), "--case", name, "--report", str(report)],
        capture_output=True, text=True,
    )
    assert finished.returncode == exit_code, finished.stderr
    assert finished.stderr == ""
    data = json.loads(report.read_text())
    assert set(data) >= {"suite", "started_at", "passed", "failed", "results", "finished_at", "run_id"}
    assert data["suite"] == ("simulated-recovery" if exit_code == 0 else "simulated-faults")
    assert (data["passed"], data["failed"]) == ((1, 0) if exit_code == 0 else (0, 1))
    assert len(data["results"]) == 1
    case = data["results"][0]
    assert set(case) == {"name", "status", "duration_ms", "details", "steps", "failure_category"}
    assert (case["name"], case["status"], case["details"]) == (name, status, details)
    assert case["duration_ms"] >= 0
    assert data["started_at"]
    assert f"[{status.upper():6}] {name}" in finished.stdout


def test_default_cli_runs_all_cases_and_writes_default_report(tmp_path):
    finished = subprocess.run(
        [sys.executable, "-m", "hil_automation.cli",
         str(ROOT / "scenarios" / "smoke.yaml")],
        cwd=tmp_path, capture_output=True, text=True,
    )
    assert finished.returncode == 0, finished.stderr
    data = json.loads((tmp_path / "reports" / "latest.json").read_text())
    assert [case["name"] for case in data["results"]] == [
        "power_rail_reaches_five_volts", "device_is_not_overheating",
        "device_responds_to_heartbeat",
    ]
    assert (data["passed"], data["failed"]) == (3, 0)
    assert "JSON report: reports/latest.json" in finished.stdout


def test_listing_preserves_existing_report(tmp_path):
    report = tmp_path / "existing.json"
    report.write_text("previous run", encoding="utf-8")
    finished = subprocess.run(
        [sys.executable, "-m", "hil_automation.cli",
         str(ROOT / "scenarios" / "smoke.yaml"), "--list-tests", "--report", str(report)],
        capture_output=True, text=True,
    )
    assert finished.returncode == 0, finished.stderr
    assert report.read_text() == "previous run"


@pytest.mark.parametrize("option", [["--list-tests"], ["--case", "anything"]])
def test_selection_options_still_validate_yaml(tmp_path, option):
    config = tmp_path / "invalid.yaml"
    config.write_text("suite: incomplete\n", encoding="utf-8")
    report = tmp_path / "invalid.json"
    finished = subprocess.run(
        [sys.executable, "-m", "hil_automation.cli", str(config),
         *option, "--report", str(report)],
        capture_output=True, text=True,
    )
    assert finished.returncode == 2
    assert "bench.type: simulated" in finished.stderr
    assert not report.exists()


def test_cli_serializes_step_tracking(tmp_path):
    report = tmp_path / "tracking.json"
    finished = subprocess.run(
        [sys.executable, "-m", "hil_automation.cli",
         str(ROOT / "scenarios" / "faults.yaml"), "--report", str(report)],
        capture_output=True, text=True,
    )
    assert finished.returncode == 1
    data = json.loads(report.read_text())
    assert [step["status"] for step in data["results"][0]["steps"]] == [
        "passed", "passed", "failed",
    ]
    assert data["results"][0]["steps"][2]["index"] == 3
    assert data["finished_at"] >= data["started_at"]
    assert data["run_id"]


def test_cli_report_error_returns_two_without_traceback(tmp_path):
    finished = subprocess.run(
        [sys.executable, "-m", "hil_automation.cli",
         str(ROOT / "scenarios" / "smoke.yaml"), "--report", str(tmp_path)],
        capture_output=True, text=True,
    )
    assert finished.returncode == 2
    assert "Error: Cannot write JSON report" in finished.stderr
    assert "Traceback" not in finished.stderr
    assert finished.stdout == ""


@pytest.mark.parametrize("scenario, passed, failed", [
    ("smoke", 3, 0), ("recovery", 3, 0), ("faults", 0, 2), ("failure_demo", 0, 2),
])
def test_scenario_report_statistics_match_results(tmp_path, scenario, passed, failed):
    output = tmp_path / f"{scenario}.json"
    finished = subprocess.run(
        [sys.executable, "-m", "hil_automation.cli",
         str(ROOT / "scenarios" / f"{scenario}.yaml"), "--report", str(output)],
        capture_output=True, text=True,
    )
    assert finished.returncode == (1 if failed else 0), finished.stderr
    data = json.loads(output.read_text())
    assert data["schema_version"] == "1.0"
    stats = data["statistics"]
    assert (stats["passed_cases"], stats["failed_cases"]) == (passed, failed)
    assert stats["total_cases"] == len(data["results"]) == passed + failed
    steps = [step for case in data["results"] for step in case["steps"]]
    assert stats["total_steps"] == len(steps)
    assert stats["executed_steps"] == sum(step["status"] != "skipped" for step in steps)
    assert sum(item["executed"] for item in data["action_statistics"].values()) == stats["executed_steps"]
    assert data["metadata"]["started_at"] == data["started_at"]
