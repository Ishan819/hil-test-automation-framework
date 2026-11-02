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
