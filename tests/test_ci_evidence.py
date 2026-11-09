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
