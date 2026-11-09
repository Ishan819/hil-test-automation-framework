"""Regression checks for the repository's CI evidence commands."""
import importlib
import json
from pathlib import Path
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def evidence(tmp_path, monkeypatch):
    monkeypatch.syspath_prepend(str(ROOT / "tools"))
    generator = importlib.import_module("ci_evidence")
    validator = importlib.import_module("validate_ci_evidence")
    output = tmp_path / "evidence"
    generator.generate(output)
    return output, generator, validator


def test_generated_evidence_validates(evidence):
    output, _, validator = evidence
    examples = validator.validate(output)
    assert [item["execution_status"] for item in examples] == ["passed", "failed"]
    assert [item["decision"] for item in examples] == ["qualified", "not_qualified"]
    assert str(output) not in (output / "index.json").read_text()


@pytest.mark.parametrize("damage", ["missing", "malformed", "case", "counts", "retry", "id", "qualification", "binary", "traversal"])
def test_rejects_incomplete_or_inconsistent_evidence(evidence, damage):
    output, _, validator = evidence
    index = json.loads((output / "index.json").read_text())
    example = index["demonstrations"][0]
    path = output / example["manifest"]
    batch = json.loads(path.read_text())
    if damage == "missing":
        path.unlink()
    elif damage == "malformed":
        path.write_text("{")
    elif damage == "qualification":
        qpath = output / example["qualification_report"]
        q = json.loads(qpath.read_text())
        q["qualified"] = False
        qpath.write_text(json.dumps(q))
    elif damage == "binary":
        (path.parent / batch["suites"][0]["report_file"]).write_bytes(b"bad")
    elif damage == "traversal":
        example["manifest"] = "../outside.json"
        (output / "index.json").write_text(json.dumps(index))
    else:
        report = batch["suites"][0]["report"]
        if damage == "case":
            report["results"][0]["name"] = "wrong"
        elif damage == "counts":
            report["passed"] += 1
        elif damage == "retry":
            report["results"][0]["retry_count"] += 1
        elif damage == "id":
            report["run_id"] = "wrong"
        path.write_text(json.dumps(batch))
    with pytest.raises((ValueError, OSError)):
        validator.validate(output)


def test_validation_cli_missing_evidence_is_failure(tmp_path):
    result = subprocess.run([sys.executable, str(ROOT / "tools/ci_evidence.py"), "validate",
                             "--output-dir", str(tmp_path)], capture_output=True, text=True)
    assert result.returncode == 2
    assert "CI evidence" in result.stderr
    assert str(tmp_path) not in result.stderr


def test_summary_uses_parsed_results_and_artifact_reference(evidence):
    output, _, validator = evidence
    examples = validator.validate(output)
    text = validator.summary(examples, "ci-evidence")
    assert "| recovery | passed | 6 | 0 | qualified |" in text
    assert "| faults | failed | 6 | 2 |" in text
    assert "expected failure" in text
    assert "Failed cases exceed the allowed maximum" in text
    examples[0]["observed"]["passed_cases"] = 123
    assert "| recovery | passed | 123 |" in validator.summary(examples, "artifact")


@pytest.mark.parametrize("message", ["<script>alert(1)</script>", "\n| forged | row |\n# Heading",
                                    "[click](javascript:alert(1))", "![secret](https://example.org)",
                                    "`code` **bold** <!-- comment -->", "\x00\x1b\u202e"])
def test_summary_encodes_untrusted_diagnostics(evidence, message):
    output, _, validator = evidence
    examples = validator.validate(output)
    examples[1]["failure_reasons"] = [message]
    text = validator.summary(examples, message)
    assert message not in text
    assert "<script>" not in text and "javascript:" not in text
    assert len([line for line in text.splitlines() if line.startswith("| ")]) == 4
    assert text.count("\n## ") == 0
    assert "\x00" not in text and "\x1b" not in text and "\u202e" not in text
    assert "&#8238;" not in text and "&#27;" not in text


def test_summary_cli_fails_closed_without_leaking_error_paths(tmp_path):
    summary = tmp_path / "summary.md"
    result = subprocess.run([sys.executable, str(ROOT / "tools/ci_evidence.py"), "summary",
                             "--output-dir", str(tmp_path / "missing"), "--summary-file", str(summary)],
                            capture_output=True, text=True)
    assert result.returncode == 2
    assert "Verification: FAILED" in summary.read_text()
    assert str(tmp_path) not in summary.read_text() + result.stderr


def test_generation_refuses_stale_evidence(evidence):
    output, generator, _ = evidence
    before = (output / "index.json").read_bytes()
    with pytest.raises(ValueError, match="empty"):
        generator.generate(output)
    assert (output / "index.json").read_bytes() == before


def test_unexpected_success_of_fault_execution_is_rejected(evidence, monkeypatch, tmp_path):
    _, generator, _ = evidence
    from types import SimpleNamespace
    demo = importlib.import_module("demo_release")
    monkeypatch.setattr(demo.subprocess, "run", lambda *args, **kwargs: SimpleNamespace(returncode=0, stderr=""))
    with pytest.raises(ValueError, match="expected 1"):
        generator.generate(tmp_path / "unexpected")


def test_workflow_keeps_failure_status_and_retains_evidence():
    import yaml
    workflow = yaml.safe_load((ROOT / ".github/workflows/tests.yml").read_text())
    job = workflow["jobs"]["pytest"]
    assert job["strategy"]["matrix"]["python-version"] == ["3.10", "3.11", "3.12"]
    steps = job["steps"]
    evidence_steps = [step for step in steps if "CI evidence" in step["name"] or step["name"] == "Upload CI test evidence"]
    assert len(evidence_steps) == 4
    assert all("continue-on-error" not in step for step in evidence_steps)
    assert all(step.get("if") == "${{ !cancelled() }}" for step in evidence_steps)
    upload = next(step for step in evidence_steps if "uses" in step)
    assert upload["uses"] == "actions/upload-artifact@v6"
    assert upload["with"]["if-no-files-found"] == "error"
    assert "native" in workflow["jobs"]


@pytest.mark.parametrize("format", ["json", "xml", "pb"])
def test_summary_cli_rejects_damaged_scenario_report(evidence, format, tmp_path):
    output, _, _ = evidence
    index = json.loads((output / "index.json").read_text())
    scenario = output / index["demonstrations"][0]["scenario_reports"]
    path = next(scenario.glob(f"*.{format}"))
    path.write_bytes(b"broken")
    summary = tmp_path / "summary.md"
    process = subprocess.run([sys.executable, str(ROOT / "tools/ci_evidence.py"), "summary",
                              "--output-dir", str(output), "--summary-file", str(summary)],
                             capture_output=True, text=True)
    assert process.returncode == 2
    assert "Verification: FAILED" in summary.read_text()
    assert "Traceback" not in process.stderr


def test_required_fields_are_not_optional(evidence):
    output, _, validator = evidence
    index = json.loads((output / "index.json").read_text())
    path = output / index["demonstrations"][0]["manifest"]
    batch = json.loads(path.read_text())
    del batch["suites"][0]["report"]["finished_at"]
    path.write_text(json.dumps(batch))
    with pytest.raises((KeyError, TypeError, ValueError)):
        validator.validate(output)


def test_validation_preserves_producing_runner_metadata(evidence):
    output, _, validator = evidence
    index = json.loads((output / "index.json").read_text())
    for example in index["demonstrations"]:
        path = output / example["manifest"]
        batch = json.loads(path.read_text())
        for suite in batch["suites"]:
            suite["report"]["metadata"].update(python_version="3.10.99", system="OtherOS", machine="other")
        path.write_text(json.dumps(batch))
    path = output / index["demonstrations"][0]["scenario_reports"] / "smoke.json"
    smoke = json.loads(path.read_text())
    smoke["metadata"].update(python_version="3.10.99", system="OtherOS", machine="other")
    path.write_text(json.dumps(smoke))
    assert len(validator.validate(output)) == 2
