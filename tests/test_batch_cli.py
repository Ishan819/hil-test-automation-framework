import json
from pathlib import Path
import subprocess
import sys

import pytest
import yaml


ROOT = Path(__file__).resolve().parents[1]


def cli(*arguments, cwd=None):
    return subprocess.run(
        [sys.executable, "-m", "hil_automation.cli", *map(str, arguments)],
        capture_output=True, text=True, cwd=cwd,
    )


@pytest.fixture
def plan(tmp_path):
    suite = tmp_path / "suite.yaml"
    suite.write_text(yaml.safe_dump({
        "suite": "alive", "bench": {"type": "simulated"},
        "tests": [{"name": "heartbeat", "steps": [{"action": "expect_heartbeat"}]}],
    }))
    plan = tmp_path / "plan.yaml"
    plan.write_text(yaml.safe_dump({"plan": "daily", "suites": ["suite.yaml"]}))
    return plan


def test_plan_cli_writes_manifest_and_individual_suite_report(plan, tmp_path):
    root = tmp_path / "reports"
    finished = cli("--plan", plan, "--report-dir", root, "--quiet")
    assert finished.returncode == 0, finished.stderr
    assert finished.stdout == "Batch results: 1 passed, 0 failed, 0 skipped\n"
    manifest = next(root.glob("*/batch.json"))
    data = json.loads(manifest.read_text())
    assert data["status"] == "passed"
    assert data["suites"][0]["report"]["passed"] == 1
    assert (manifest.parent / data["suites"][0]["report_file"]).is_file()


@pytest.mark.parametrize("options", [
    ["suite.yaml"], ["--native-tests", "unused"], ["--native-results"],
    ["--native-filter", "Suite.*"], ["--native-timeout", "1"],
    ["--case", "one"], ["--tag", "smoke"], ["--list-tests"], ["--report", "unused.json"],
])
def test_plan_incompatible_options_are_rejected(options):
    finished = cli("--plan", "missing.yaml", *options)
    assert finished.returncode == 2
    assert "--plan cannot be combined" in finished.stderr


def test_report_directory_requires_plan():
    finished = cli("missing.yaml", "--report-dir", "unused")
    assert finished.returncode == 2
    assert "--report-dir requires --plan" in finished.stderr


@pytest.mark.parametrize("report_format, extension", [("json", "json"), ("junit", "xml"), ("protobuf", "pb")])
def test_successful_batch_preserves_order_ids_and_all_report_formats(tmp_path, report_format, extension):
    from xml.etree import ElementTree as ET
    from hil_automation.protobuf import parse_result

    root = tmp_path / "reports"
    finished = cli(
        "--plan", ROOT / "plans/recovery.yaml", "--report-dir", root,
        "--report-format", report_format, cwd=tmp_path,
    )
    assert finished.returncode == 0, finished.stderr
    manifest = next(root.glob("*/batch.json"))
    data = json.loads(manifest.read_text())
    assert data["status"] == "passed"
    assert [suite["suite"] for suite in data["suites"]] == ["bench-smoke-tests", "simulated-recovery"]
    assert data["statistics"]["total_cases"] == data["statistics"]["passed_cases"] == 6
    assert len({data["run_id"], *(suite["report"]["run_id"] for suite in data["suites"])}) == 3
    for index, suite in enumerate(data["suites"], start=1):
        assert suite["report_file"] == f"{index:03d}.{extension}"
        path = manifest.parent / suite["report_file"]
        if report_format == "json":
            assert json.loads(path.read_text()) == suite["report"]
        elif report_format == "junit":
            assert ET.parse(path).getroot().get("tests") == "3"
        else:
            assert parse_result(path.read_bytes()).summary.passed == 3


@pytest.mark.parametrize("fail_fast", [False, True])
def test_mixed_batch_failure_exit_and_skipped_outcomes(tmp_path, fail_fast):
    root = tmp_path / "reports"
    args = ["--fail-fast"] if fail_fast else []
    finished = cli("--plan", ROOT / "plans/faults.yaml", "--report-dir", root, *args)
    assert finished.returncode == 1, finished.stderr
    data = json.loads(next(root.glob("*/batch.json")).read_text())
    assert data["status"] == "failed"
    assert [suite["status"] for suite in data["suites"]] == (
        ["passed", "failed", "skipped"] if fail_fast else ["passed", "failed", "passed"]
    )
    stats = data["statistics"]
    assert stats["total_cases"] == 8
    assert (stats["passed_cases"], stats["failed_cases"], stats["skipped_cases"]) == (
        (3, 1, 4) if fail_fast else (6, 2, 0)
    )
    if fail_fast:
        assert data["suites"][2]["report"] is None and data["suites"][2]["report_file"] is None


def test_batch_cli_preserves_bench_state_isolation_and_retry_history(tmp_path):
    cases = [
        {"name": "mutate", "steps": [
            {"action": "set_voltage", "value": 12}, {"action": "set_temperature", "value": 95},
            {"action": "set_connection", "connected": False},
        ]},
        {"name": "fresh", "steps": [
            {"action": "expect_voltage", "value": 0, "tolerance": 0},
            {"action": "expect_temperature_below", "limit_c": 30}, {"action": "expect_heartbeat"},
        ]},
        {"name": "retries", "retries": 1, "steps": [{"action": "expect_temperature_below", "limit_c": 0}]},
    ]
    for index, case in enumerate(cases):
        (tmp_path / f"{index}.yaml").write_text(yaml.safe_dump({
            "suite": "same-display-name", "bench": {"type": "simulated"}, "tests": [case],
        }))
    plan = tmp_path / "isolated.yaml"
    plan.write_text(yaml.safe_dump({"plan": "isolated", "suites": [f"{i}.yaml" for i in range(3)]}))
    root = tmp_path / "reports"
    for _ in range(2):
        finished = cli("--plan", plan, "--report-dir", root, "--quiet")
        assert finished.returncode == 1, finished.stderr
    manifests = list(root.glob("*/batch.json"))
    assert len(manifests) == 2
    for manifest in manifests:
        data = json.loads(manifest.read_text())
        assert [suite["status"] for suite in data["suites"]] == ["passed", "passed", "failed"]
        assert len(data["suites"][2]["report"]["results"][0]["attempts"]) == 2
        assert len({suite["report_file"] for suite in data["suites"]}) == 3


def test_invalid_plan_is_fully_validated_before_any_suite_runs(tmp_path, monkeypatch, capsys):
    from hil_automation import cli as module

    (tmp_path / "invalid.yaml").write_text("suite: missing-bench")
    plan = tmp_path / "invalid-plan.yaml"
    plan.write_text(yaml.safe_dump({"plan": "invalid", "suites": ["invalid.yaml"]}))
    def unexpected(*args, **kwargs):
        raise AssertionError("Invalid plans must not execute suites")
    monkeypatch.setattr(module, "run_plan", unexpected)
    monkeypatch.setattr(sys, "argv", ["hil-run", "--plan", str(plan)])
    assert module.main() == 2
    assert "Invalid plan suite" in capsys.readouterr().err


def test_batch_output_error_does_not_print_success(plan, tmp_path):
    root = tmp_path / "file"
    root.write_text("existing")
    finished = cli("--plan", plan, "--report-dir", root, "--quiet")
    assert finished.returncode == 2
    assert "Cannot write batch report" in finished.stderr
    assert "passed" not in finished.stdout
    assert root.read_text() == "existing"
