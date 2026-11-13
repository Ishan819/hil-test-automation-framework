import json
from pathlib import Path
import subprocess
import sys

from hil_automation.protobuf import parse_result

SCRIPT = Path(__file__).resolve().parents[1] / "tools/demo_release.py"


def test_demo_runs_from_any_directory_and_exports_both_decisions(tmp_path):
    for _ in range(2):
        process = subprocess.run([sys.executable, str(SCRIPT), "--output-dir", str(tmp_path / "reports")],
                                 cwd=tmp_path, capture_output=True, text=True)
        assert process.returncode == 0, process.stderr
        examples = json.loads(process.stdout)["demonstrations"]
        assert [e["decision"] for e in examples] == ["qualified", "not_qualified"]
        assert [e["execution_status"] for e in examples] == ["passed", "failed"]
        assert [e["observed"]["failed_cases"] for e in examples] == [0, 2]
        for example in examples:
            manifest = Path(example["manifest"])
            batch = json.loads(manifest.read_text())
            qualification = json.loads(Path(example["qualification_report"]).read_text())
            assert qualification["decision"] == example["decision"]
            assert qualification["criteria"] == example["criteria"]
            assert batch["run_id"] == example["execution_references"][0]["run_id"]
            for suite in batch["suites"]:
                message = parse_result((manifest.parent / suite["report_file"]).read_bytes())
                assert message.run_id == suite["report"]["run_id"]
    assert len(list((tmp_path / "reports").glob("*/batch.json"))) == 4


def test_demo_publication_failure_returns_error(tmp_path):
    output = tmp_path / "occupied"
    output.write_text("preserve me")
    process = subprocess.run([sys.executable, str(SCRIPT), "--output-dir", str(output)],
                             capture_output=True, text=True)
    assert process.returncode == 2 and "Demo failed" in process.stderr
    assert not process.stdout
    assert output.read_text() == "preserve me"


def test_demo_exports_three_single_suite_formats(tmp_path):
    from xml.etree import ElementTree as ET

    process = subprocess.run([sys.executable, str(SCRIPT), "--output-dir", str(tmp_path)],
                             capture_output=True, text=True)
    assert process.returncode == 0, process.stderr
    examples = json.loads(process.stdout)["demonstrations"]
    directory = Path(examples[0]["scenario_reports"])
    assert json.loads((directory / "smoke.json").read_text())["passed"] == 3
    faults = ET.parse(directory / "faults.xml").getroot()
    assert faults.get("failures") == "2"
    assert parse_result((directory / "recovery.pb").read_bytes()).summary.passed == 3


def test_demo_refuses_symlinked_scenario_directory(tmp_path, monkeypatch):
    import importlib
    import pytest

    monkeypatch.syspath_prepend(str(SCRIPT.parent))
    demo = importlib.import_module("demo_release")
    output = tmp_path / "reports"
    output.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    (output / "scenarios").symlink_to(outside, target_is_directory=True)
    with pytest.raises(ValueError, match="symbolic link"):
        demo.demonstrate(output, 2)
    assert not list(outside.iterdir())


def test_demo_verifies_reports_instead_of_only_decision_booleans(tmp_path, monkeypatch):
    import importlib
    import pytest

    monkeypatch.syspath_prepend(str(SCRIPT.parent))
    demo = importlib.import_module("demo_release")
    original = demo.subprocess.run
    output = tmp_path / "reports"
    def corrupt_after_last_execution(command, **kwargs):
        result = original(command, **kwargs)
        if "--plan" in command and any(str(argument).endswith("plans/faults.yaml") for argument in command):
            next(output.glob("*/*.pb")).unlink()
        return result
    monkeypatch.setattr(demo.subprocess, "run", corrupt_after_last_execution)
    with pytest.raises(ValueError, match="evidence"):
        demo.demonstrate(output, 2)


def test_demo_timeout_is_reported_as_incomplete_evidence(tmp_path, monkeypatch):
    import importlib
    import pytest

    monkeypatch.syspath_prepend(str(SCRIPT.parent))
    demo = importlib.import_module("demo_release")
    def timeout(command, **kwargs):
        assert kwargs["timeout"] == 120
        raise subprocess.TimeoutExpired(command, 120)
    monkeypatch.setattr(demo.subprocess, "run", timeout)
    with pytest.raises(ValueError, match="timed out"):
        demo.demonstrate(tmp_path / "reports", 1)


def test_demo_supports_sequential_execution_with_the_same_evidence_checks(tmp_path):
    result = subprocess.run([sys.executable, str(SCRIPT), "--workers", "1", "--output-dir", str(tmp_path)],
                            capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    examples = json.loads(result.stdout)["demonstrations"]
    for example in examples:
        assert json.loads(Path(example["manifest"]).read_text())["workers"] == 1
    assert [item["decision"] for item in examples] == ["qualified", "not_qualified"]
