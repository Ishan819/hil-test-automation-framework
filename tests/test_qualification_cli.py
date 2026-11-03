import json
import sys

import pytest

from test_batch_cli import ROOT, cli


@pytest.fixture
def policy(tmp_path):
    path = tmp_path / "policy.yaml"
    path.write_text("{}")
    return path


def test_cli_qualification_is_opt_in_and_writes_separate_json(policy, tmp_path):
    root = tmp_path / "reports"
    result = cli("--plan", ROOT / "plans/recovery.yaml", "--qualification-policy", policy,
                 "--report-dir", root, "--quiet")
    assert result.returncode == 0, result.stderr
    assert result.stdout == "Batch results: 2 passed, 0 failed, 0 skipped\nQualification: qualified\n"
    path = next(root.glob("*/qualification.json"))
    data = json.loads(path.read_text())
    assert data["qualified"] and data["observed"]["passed_cases"] == 6
    batch = json.loads(path.with_name("batch.json").read_text())
    assert data["execution_references"][0]["run_id"] == batch["run_id"]


@pytest.mark.parametrize("options", [[], ["missing.yaml"], ["--native-tests", "unused"], ["missing.yaml", "--list-tests"]])
def test_qualification_policy_requires_plan(policy, options):
    result = cli(*options, "--qualification-policy", policy)
    assert result.returncode == 2
    assert "--qualification-policy requires --plan" in result.stderr


def test_invalid_policy_prevents_any_execution_or_output(policy, tmp_path, monkeypatch, capsys):
    from hil_automation import cli as module

    policy.write_text("max_failed_cases: true")
    def unexpected(*args, **kwargs):
        pytest.fail("Invalid policies must be rejected before running tests")
    monkeypatch.setattr(module, "run_plan", unexpected)
    root = tmp_path / "reports"
    monkeypatch.setattr(sys, "argv", ["hil-run", "--plan", str(ROOT / "plans/recovery.yaml"),
                                      "--qualification-policy", str(policy), "--report-dir", str(root)])
    assert module.main() == 2
    captured = capsys.readouterr()
    assert "max_failed_cases must be a non-negative integer" in captured.err
    assert not captured.out and not root.exists()


def test_cli_preserves_execution_failure_exit_with_lenient_policy(policy, tmp_path):
    policy.write_text("min_pass_percentage: 50\nmax_failed_cases: 2\n")
    result = cli("--plan", ROOT / "plans/faults.yaml", "--qualification-policy", policy,
                 "--report-dir", tmp_path / "reports", "--quiet")
    assert result.returncode == 1
    assert "Qualification: qualified" in result.stdout
    assert "1 failed" in result.stdout
