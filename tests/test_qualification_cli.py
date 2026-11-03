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


@pytest.mark.parametrize("workers", [1, 2])
@pytest.mark.parametrize("report_format", ["json", "junit", "protobuf"])
@pytest.mark.parametrize("plan, code, counts", [("recovery.yaml", 0, (6, 0)), ("faults.yaml", 1, (6, 2))])
def test_qualification_through_real_cli_preserves_all_report_formats(policy, tmp_path, workers, report_format, plan, code, counts):
    from xml.etree import ElementTree as ET
    from hil_automation.protobuf import parse_result

    root = tmp_path / "reports"
    result = cli("--plan", ROOT / "plans" / plan, "--qualification-policy", policy,
                 "--workers", workers, "--report-format", report_format, "--report-dir", root)
    assert result.returncode == code, result.stderr
    path = next(root.glob("*/qualification.json"))
    qualification = json.loads(path.read_text())
    batch = json.loads(path.with_name("batch.json").read_text())
    assert qualification["qualified"] == (code == 0)
    assert qualification["complete_evidence"]
    observed = qualification["observed"]
    assert (observed["passed_cases"], observed["failed_cases"]) == counts
    assert observed["total_cases"] == sum(counts)
    assert observed["incomplete_cases"] == 0
    for reference, item in zip(qualification["execution_references"][1:], batch["suites"]):
        assert reference["run_id"] == item["report"]["run_id"]
        report = path.parent / item["report_file"]
        if report_format == "json":
            assert json.loads(report.read_text())["run_id"] == reference["run_id"]
        elif report_format == "junit":
            assert ET.parse(report).getroot().get("id") == reference["run_id"]
        else:
            assert parse_result(report.read_bytes()).run_id == reference["run_id"]


@pytest.mark.parametrize("allow_recovered", [False, True])
@pytest.mark.parametrize("workers", [1, 2])
def test_cli_evaluates_actual_retry_recovery(policy, tmp_path, monkeypatch, capsys, allow_recovered, workers):
    from threading import Lock
    import yaml
    from hil_automation import cli as module, runner

    for index in (1, 2):
        (tmp_path / f"suite{index}.yaml").write_text(yaml.safe_dump({
            "suite": f"recovery-{index}", "bench": {"type": "simulated", "initial_voltage": index},
            "tests": [{"name": "recovered", "retries": 1, "steps": [{"action": "expect_heartbeat"}]}],
        }))
    plan = tmp_path / "recovery.yaml"
    plan.write_text("plan: recovery\nsuites: [suite1.yaml, suite2.yaml]\n")
    policy.write_text(f"allow_recovered: {str(allow_recovered).lower()}\n")
    original, calls, lock = runner.make_bench, {}, Lock()
    def make(config):
        bench = original(config)
        with lock:
            key = config["initial_voltage"]
            calls[key] = calls.get(key, 0) + 1
            bench.set_connected(calls[key] > 1)
        return bench
    monkeypatch.setattr(runner, "make_bench", make)
    root = tmp_path / "reports"
    monkeypatch.setattr(sys, "argv", ["hil-run", "--plan", str(plan), "--workers", str(workers),
                                      "--qualification-policy", str(policy), "--report-dir", str(root), "--quiet"])
    assert module.main() == (0 if allow_recovered else 1)
    assert "Batch results: 2 passed, 0 failed, 0 skipped" in capsys.readouterr().out
    data = json.loads(next(root.glob("*/qualification.json")).read_text())
    assert data["qualified"] == allow_recovered
    assert data["observed"]["recovered_cases"] == data["observed"]["total_cases"] == 2
    assert calls == {1: 2, 2: 2}


@pytest.mark.parametrize("damage", ["empty", "missing_suite", "missing_cases"])
def test_cli_never_qualifies_missing_completed_evidence(policy, tmp_path, monkeypatch, capsys, damage):
    from hil_automation import cli as module

    original = module.run_plan
    def damaged(plan, **kwargs):
        batch = original(plan, **kwargs)
        if damage == "empty":
            batch.suites.clear()
        elif damage == "missing_suite":
            batch.suites.pop()
        else:
            batch.suites[0].report.results.clear()
        return batch
    policy.write_text("min_pass_percentage: 0\nmax_failed_cases: 100\nallow_skipped: true\nallow_recovered: true\n")
    monkeypatch.setattr(module, "run_plan", damaged)
    root = tmp_path / "reports"
    monkeypatch.setattr(sys, "argv", ["hil-run", "--plan", str(ROOT / "plans/recovery.yaml"),
                                      "--qualification-policy", str(policy), "--report-dir", str(root)])
    assert module.main() == 1
    assert "Qualification: not qualified" in capsys.readouterr().out
    data = json.loads(next(root.glob("*/qualification.json")).read_text())
    assert not data["qualified"] and not data["complete_evidence"]
    assert data["observed"]["incomplete_cases"] > 0


def test_sequential_and_parallel_qualification_decisions_are_deterministic(policy, tmp_path):
    documents = []
    for workers in (1, 2):
        root = tmp_path / str(workers)
        result = cli("--plan", ROOT / "plans/faults.yaml", "--qualification-policy", policy,
                     "--workers", workers, "--report-dir", root)
        assert result.returncode == 1
        documents.append(json.loads(next(root.glob("*/qualification.json")).read_text()))
    for field in ("decision", "policy", "observed", "criteria", "evidence_issues", "failure_reasons"):
        assert documents[0][field] == documents[1][field]
