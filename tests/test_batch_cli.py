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
