import json
import sys

import pytest
import yaml

from test_batch_cli import ROOT, cli


@pytest.mark.parametrize("workers", ["0", "-1", "9", "true", "1.5"])
def test_cli_rejects_invalid_worker_counts_without_reports(tmp_path, workers):
    root = tmp_path / "reports"
    finished = cli("--plan", ROOT / "plans/recovery.yaml", "--workers", workers, "--report-dir", root)
    assert finished.returncode == 2
    assert "Workers must be an integer" in finished.stderr or "invalid int value" in finished.stderr
    assert not root.exists()
    assert "Batch results" not in finished.stdout


@pytest.mark.parametrize("options", [[], ["missing.yaml"], ["--native-tests", "unused"], ["missing.yaml", "--list-tests"]])
def test_workers_require_batch_mode(options):
    finished = cli(*options, "--workers", "2")
    assert finished.returncode == 2
    assert "--workers requires --plan" in finished.stderr


def test_parallel_fail_fast_cli_is_rejected(tmp_path):
    root = tmp_path / "reports"
    finished = cli("--plan", ROOT / "plans/faults.yaml", "--workers", "2", "--fail-fast", "--report-dir", root)
    assert finished.returncode == 2
    assert "Parallel execution does not support fail-fast; use one worker" in finished.stderr
    assert not root.exists()


def test_cli_workers_override_plan_configuration(tmp_path):
    source = ROOT / "plans/recovery.yaml"
    payload = yaml.safe_load(source.read_text())
    payload["suites"] = [str((source.parent / path).resolve().relative_to(ROOT)) for path in payload["suites"]]
    # Keep plan references relative while loading from this temporary directory.
    import os
    payload["suites"] = [os.path.relpath(ROOT / path, tmp_path) for path in payload["suites"]]
    payload["workers"] = 2
    plan = tmp_path / "parallel.yaml"
    plan.write_text(yaml.safe_dump(payload))
    root = tmp_path / "reports"
    for flags, expected in [([], 2), (["--workers", "1"], 1)]:
        finished = cli("--plan", plan, "--report-dir", root, *flags)
        assert finished.returncode == 0, finished.stderr
        manifest = max(root.glob("*/batch.json"), key=lambda path: path.stat().st_mtime_ns)
        assert json.loads(manifest.read_text())["workers"] == expected


def test_worker_exception_is_visible_in_cli_and_manifest(tmp_path, monkeypatch, capsys):
    from hil_automation import cli as module, orchestration

    original = orchestration.run_suite
    def run(suite):
        if suite.name == "bench-smoke-tests":
            raise RuntimeError("injected simulator bug")
        return original(suite)
    monkeypatch.setattr(orchestration, "run_suite", run)
    root = tmp_path / "reports"
    monkeypatch.setattr(sys, "argv", ["hil-run", "--plan", str(ROOT / "plans/recovery.yaml"),
                                      "--workers", "2", "--report-dir", str(root)])
    assert module.main() == 1
    captured = capsys.readouterr()
    assert "RuntimeError: injected simulator bug" in captured.out
    assert "Batch results: 1 passed, 1 failed, 0 skipped" in captured.out
    data = json.loads(next(root.glob("*/batch.json")).read_text())
    assert data["suites"][0]["report_file"] is None
    assert data["suites"][1]["report"]["passed"] == 3


@pytest.mark.parametrize("workers", [1, 2, 8])
@pytest.mark.parametrize("plan, code, statuses, counts", [
    ("recovery.yaml", 0, ["passed", "passed"], (6, 0)),
    ("faults.yaml", 1, ["passed", "failed", "passed"], (6, 2)),
])
@pytest.mark.parametrize("report_format", ["json", "junit", "protobuf"])
def test_real_cli_sequential_and_parallel_reports(tmp_path, workers, plan, code, statuses, counts, report_format):
    from xml.etree import ElementTree as ET
    from hil_automation.protobuf import parse_result

    root = tmp_path / "reports"
    for _ in range(2):
        finished = cli("--plan", ROOT / "plans" / plan, "--workers", workers,
                       "--report-dir", root, "--report-format", report_format, "--quiet")
        assert finished.returncode == code, finished.stderr
        assert finished.stderr == ""
        assert "Batch results:" in finished.stdout
    manifests = list(root.glob("*/batch.json"))
    assert len(manifests) == 2
    run_ids = set()
    for manifest in manifests:
        data = json.loads(manifest.read_text())
        assert data["workers"] == workers
        assert [item["status"] for item in data["suites"]] == statuses
        stats = data["statistics"]
        assert (stats["passed_cases"], stats["failed_cases"]) == counts
        assert stats["total_cases"] == stats["executed_cases"] == sum(counts)
        assert stats["skipped_cases"] == stats["unreported_cases"] == 0
        run_ids.add(data["run_id"])
        for item in data["suites"]:
            report = item["report"]
            run_ids.add(report["run_id"])
            path = manifest.parent / item["report_file"]
            assert path.is_file()
            if report_format == "json":
                assert json.loads(path.read_text()) == report
            elif report_format == "junit":
                suite = ET.parse(path).getroot()
                assert suite.get("id") == report["run_id"]
                assert suite.get("name") == item["suite"]
                assert int(suite.get("tests")) == item["planned_cases"]
                assert int(suite.get("failures")) == report["failed"]
            else:
                result = parse_result(path.read_bytes())
                assert result.run_id == report["run_id"] and result.suite == item["suite"]
                assert (result.summary.passed, result.summary.failed) == (report["passed"], report["failed"])
    assert len(run_ids) == 2 * (len(statuses) + 1)


def test_parallel_cli_output_failure_returns_two_without_success(tmp_path):
    root = tmp_path / "existing"
    root.write_text("keep")
    finished = cli("--plan", ROOT / "plans/recovery.yaml", "--workers", "2", "--report-dir", root)
    assert finished.returncode == 2
    assert "Cannot write batch report" in finished.stderr
    assert not finished.stdout
    assert root.read_text() == "keep"
