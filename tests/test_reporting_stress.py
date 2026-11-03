"""Exercise repeated publication, qualification association and atomic failures."""
import json
from concurrent.futures import ThreadPoolExecutor

import pytest

from hil_automation.orchestration import run_plan, write_batch_report
from hil_automation.plans import ExecutionPlan
from hil_automation.protobuf import parse_result
from hil_automation.qualification import evaluate_qualification
from hil_automation.qualification_policy import QualificationPolicy
from hil_automation.reporting import ReportError, write_qualification_report
from test_parallel import entry


@pytest.mark.parametrize("report_format", ["json", "protobuf"])
def test_repeated_concurrent_reports_and_rejected_qualification(tmp_path, report_format):
    plan = ExecutionPlan("mixed", [entry("pass"), entry("fail", [
        {"action": "expect_temperature_below", "limit_c": 0},
    ], retries=2)], 2)
    def publish(_):
        batch = run_plan(plan)
        manifest = write_batch_report(batch, tmp_path, report_format)
        qualification = evaluate_qualification(batch, QualificationPolicy(), expected=plan)
        write_qualification_report(qualification, manifest.parent / "qualification.json")
        return manifest
    with ThreadPoolExecutor(max_workers=3) as executor:
        manifests = list(executor.map(publish, range(12)))
    assert len({m.parent for m in manifests}) == 12
    ids = set()
    for manifest in manifests:
        data = json.loads(manifest.read_text())
        assert data["status"] == "failed"
        assert data["statistics"]["total_cases"] == 2
        assert data["statistics"]["failed_cases"] == 1
        current = [data["run_id"]]
        for item in data["suites"]:
            path = manifest.parent / item["report_file"]
            expected = item["report"]
            current.append(expected["run_id"])
            if report_format == "json":
                assert json.loads(path.read_text()) == expected
            else:
                message = parse_result(path.read_bytes())
                assert message.run_id == expected["run_id"]
                assert message.suite == item["suite"]
                assert len(message.cases) == 1
                assert message.summary.failed == expected["failed"]
        qualification = json.loads((manifest.parent / "qualification.json").read_text())
        assert qualification["qualified"] is False
        assert qualification["complete_evidence"] is True
        assert qualification["observed"]["failed_cases"] == 1
        assert [r["run_id"] for r in qualification["execution_references"]] == current
        assert len(set(current)) == 3 and not ids.intersection(current)
        ids.update(current)
    assert not list(tmp_path.rglob("*.tmp"))


@pytest.mark.parametrize("report_format", ["json", "protobuf"])
def test_repeated_atomic_report_failure_keeps_complete_files_only(tmp_path, monkeypatch, report_format):
    from hil_automation import reporting
    original = reporting.os.replace
    def fail_second(source, destination):
        if destination.stem == "002":
            raise OSError("injected publication failure")
        original(source, destination)
    monkeypatch.setattr(reporting.os, "replace", fail_second)
    for _ in range(6):
        batch = run_plan(ExecutionPlan("disk", [entry("one"), entry("two")], 2))
        with pytest.raises(ReportError, match="publication failure"):
            write_batch_report(batch, tmp_path, report_format)
        directory = tmp_path / batch.run_id
        assert not (directory / "batch.json").exists()
        files = list(directory.iterdir())
        assert len(files) == 1 and files[0].stem == "001"
        if report_format == "json":
            assert json.loads(files[0].read_text())["run_id"] == batch.suites[0].report.run_id
        else:
            assert parse_result(files[0].read_bytes()).run_id == batch.suites[0].report.run_id
    assert not list(tmp_path.rglob("*.tmp"))
