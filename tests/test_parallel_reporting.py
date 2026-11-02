import json
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest

from hil_automation.orchestration import run_plan, write_batch_report
from hil_automation.plans import ExecutionPlan
from hil_automation.reporting import ReportError
from test_parallel import entry


def test_parallel_batches_with_duplicate_display_names_have_unique_outputs(tmp_path):
    first, second = entry("first"), entry("second")
    object.__setattr__(second.suite, "name", first.suite.name)
    plan = ExecutionPlan("same-names", [first, second], 2)
    barrier = Barrier(2)
    def write():
        batch = run_plan(plan)
        barrier.wait(timeout=10)
        return write_batch_report(batch, tmp_path)
    with ThreadPoolExecutor(max_workers=2) as executor:
        manifests = list(executor.map(lambda _: write(), range(2)))
    assert manifests[0].parent != manifests[1].parent
    ids = set()
    for manifest in manifests:
        data = json.loads(manifest.read_text())
        for index, item in enumerate(data["suites"], start=1):
            assert item["report_file"] == f"{index:03d}.json"
            report = json.loads((manifest.parent / item["report_file"]).read_text())
            assert report == item["report"]
            assert report["results"][0]["name"] == ["first", "second"][index - 1]
            ids.add(report["run_id"])
        assert not list(manifest.parent.glob("*.tmp"))
    assert len(ids) == 4


@pytest.mark.parametrize("corruption", ["id", "association"])
def test_report_association_errors_are_rejected_before_writing(tmp_path, corruption):
    batch = run_plan(ExecutionPlan("bad", [entry("one"), entry("two")], 2))
    if corruption == "id":
        batch.suites[1].report.run_id = batch.suites[0].report.run_id
    else:
        batch.suites[1].report.suite = "wrong"
    with pytest.raises(ReportError, match="unique run IDs|association"):
        write_batch_report(batch, tmp_path / "reports")
    assert not (tmp_path / "reports").exists()


def test_concurrent_publication_of_same_batch_cannot_overwrite(tmp_path):
    batch = run_plan(ExecutionPlan("same", [entry("one"), entry("two")], 2))
    barrier = Barrier(2)
    def write():
        barrier.wait(timeout=10)
        try:
            return write_batch_report(batch, tmp_path)
        except ReportError:
            return None
    with ThreadPoolExecutor(max_workers=2) as executor:
        outputs = list(executor.map(lambda _: write(), range(2)))
    assert sum(path is not None for path in outputs) == 1
    manifest = next(path for path in outputs if path is not None)
    data = json.loads(manifest.read_text())
    assert all(json.loads((manifest.parent / item["report_file"]).read_text()) == item["report"]
               for item in data["suites"])


def test_suite_write_failure_does_not_publish_success_manifest(tmp_path, monkeypatch):
    from hil_automation import reporting

    original = reporting._atomic_write
    def write(path, content):
        if path.name == "002.json":
            raise OSError("simulated disk failure")
        original(path, content)
    monkeypatch.setattr(reporting, "_atomic_write", write)
    batch = run_plan(ExecutionPlan("disk", [entry("one"), entry("two")], 2))
    with pytest.raises(ReportError, match="simulated disk failure"):
        write_batch_report(batch, tmp_path)
    assert not list(tmp_path.glob("*/batch.json"))
    assert json.loads(next(tmp_path.glob("*/001.json")).read_text())["suite"] == "one"


def test_worker_failure_retains_successes_and_reports_unknown_case_outcomes(tmp_path, monkeypatch):
    from hil_automation import orchestration

    original = orchestration.run_suite
    barrier = Barrier(2)
    def run(suite):
        if suite.name in ("broken", "healthy"):
            barrier.wait(timeout=10)
        if suite.name == "broken":
            raise RuntimeError("simulator unavailable")
        return original(suite)
    monkeypatch.setattr(orchestration, "run_suite", run)
    batch = run_plan(ExecutionPlan("failure", [entry("broken"), entry("healthy"), entry("later")], 2))
    assert batch.status == "failed"
    assert [suite.status for suite in batch.suites] == ["failed", "passed", "passed"]
    assert batch.suites[0].error == "RuntimeError: simulator unavailable"
    assert batch.suites[0].duration_ms >= 0
    manifest = write_batch_report(batch, tmp_path)
    data = json.loads(manifest.read_text())
    failed = data["suites"][0]
    assert failed["report"] is None and failed["report_file"] is None
    assert failed["error"] == "RuntimeError: simulator unavailable"
    stats = data["statistics"]
    assert (stats["executed_suites"], stats["failed_suites"], stats["passed_suites"]) == (3, 1, 2)
    assert (stats["executed_cases"], stats["passed_cases"], stats["failed_cases"]) == (2, 2, 0)
    assert stats["unreported_cases"] == 1 and stats["skipped_cases"] == 0
    assert stats["total_cases"] == sum(stats[key] for key in (
        "passed_cases", "failed_cases", "skipped_cases", "unreported_cases",
    ))
    assert not (manifest.parent / "001.json").exists()
    assert (manifest.parent / "002.json").is_file()
    assert (manifest.parent / "003.json").is_file()


@pytest.mark.parametrize("report_format, extension", [("json", "json"), ("junit", "xml"), ("protobuf", "pb")])
def test_parallel_aggregate_and_individual_reports_remain_consistent(tmp_path, report_format, extension):
    from xml.etree import ElementTree as ET
    from hil_automation.protobuf import parse_result

    batch = run_plan(ExecutionPlan("formats", [entry("healthy"), entry(
        "retry", [{"action": "expect_temperature_below", "limit_c": 0}], retries=2,
    )], 2))
    manifest = write_batch_report(batch, tmp_path, report_format)
    data = json.loads(manifest.read_text())
    assert data["workers"] == 2
    stats = data["statistics"]
    assert (stats["total_suites"], stats["executed_suites"], stats["passed_suites"], stats["failed_suites"]) == (2, 2, 1, 1)
    assert (stats["total_cases"], stats["executed_cases"], stats["passed_cases"], stats["failed_cases"]) == (2, 2, 1, 1)
    assert stats["unreported_cases"] == stats["skipped_cases"] == 0
    assert len({data["run_id"], *(item["report"]["run_id"] for item in data["suites"])}) == 3
    assert data["finished_at"] >= data["started_at"]
    assert data["duration_ms"] >= 0
    for index, item in enumerate(data["suites"], start=1):
        report = item["report"]
        assert item["duration_ms"] == report["duration_ms"] >= 0
        assert item["report_file"] == f"{index:03d}.{extension}"
        path = manifest.parent / item["report_file"]
        if report_format == "json":
            assert json.loads(path.read_text()) == report
        elif report_format == "junit":
            root = ET.parse(path).getroot()
            assert root.get("name") == item["suite"]
            assert root.get("id") == report["run_id"]
            assert root.get("tests") == "1"
            assert root.get("failures") == str(report["failed"])
            if index == 2:
                assert json.loads(root.find("testcase/system-out").text)["retry_count"] == 2
        else:
            message = parse_result(path.read_bytes())
            assert message.run_id == report["run_id"] and message.suite == item["suite"]
            assert message.summary.failed == report["failed"]
            if index == 2:
                history = json.loads(message.cases[0].details.split("\nRetry history: ", 1)[1])
                assert history["retry_count"] == 2
        if index == 2:
            assert report["retry_summary"] == {"total_attempts": 3, "retries": 2, "passed_after_retry": 0}


def test_batch_elapsed_time_uses_wall_clock_instead_of_summing_suites(monkeypatch):
    from hil_automation import orchestration

    original = orchestration.run_suite
    def run(suite, **kwargs):
        report = original(suite, **kwargs)
        report.duration_ms = 250
        return report
    monkeypatch.setattr(orchestration, "run_suite", run)
    monkeypatch.setattr(orchestration, "perf_counter", lambda: 10.0)
    batch = run_plan(ExecutionPlan("wall", [entry("one"), entry("two")], 2))
    assert batch.duration_ms == 0
    assert sum(suite.duration_ms for suite in batch.suites) == 500
    assert batch.workers == 2
    assert run_plan(ExecutionPlan("default", [entry("one")])).workers == 1
