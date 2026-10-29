from hil_automation.config import Suite, TestCase as HilTestCase
from hil_automation.proto import hil_results_pb2 as pb
from hil_automation.protobuf import parse_result
from hil_automation.reporting import protobuf_report
from hil_automation.runner import run_suite


def test_protobuf_report_uses_existing_actual_report_model():
    report = run_suite(Suite("binary-report", {}, [
        HilTestCase("healthy", [{"action": "expect_heartbeat"}]),
        HilTestCase("hot", [{"action": "expect_temperature_below", "limit_c": 0}]),
    ]))
    message = parse_result(protobuf_report(report))
    assert message.run_id == report.run_id
    assert message.summary.total == 2
    assert (message.summary.passed, message.summary.failed) == (1, 1)
    assert message.cases[0].status == pb.PASSED
    assert message.cases[1].details == report.results[1].details
    assert message.cases[1].steps[0].failure_category == "assertion_failure"
    assert message.started_at == report.started_at
    assert message.summary.duration_ms == report.duration_ms


def test_native_protobuf_mapping_preserves_failures_skips_and_disabled(gtest_executable):
    from hil_automation.native import run_native_tests
    from hil_automation.reporting import native_report

    binary = gtest_executable("""<testsuite name="Native">
      <testcase name="Good" time="0.001"/>
      <testcase name="Bad" time="0.01"><failure message="expected &lt; 5"/></testcase>
      <testcase name="Skip" result="skipped"><skipped message="not ready"/></testcase>
      <testcase name="DISABLED_Later" status="notrun"/>
    </testsuite>""", exit_code=1)
    report = native_report(run_native_tests(binary, capture_xml=True))
    decoded = parse_result(protobuf_report(report))
    assert [case.name for case in decoded.cases] == ["Good", "Bad", "Skip", "DISABLED_Later"]
    assert [case.status for case in decoded.cases] == [pb.PASSED, pb.FAILED, pb.SKIPPED, pb.DISABLED]
    assert all(case.origin == pb.NATIVE for case in decoded.cases)
    assert all(not case.steps for case in decoded.cases)
    assert decoded.cases[1].details == "expected < 5"
    assert decoded.cases[1].duration_ms == 10
    assert decoded.native_exit_code == 1
    assert (decoded.summary.total, decoded.summary.passed, decoded.summary.failed, decoded.summary.skipped) == (4, 1, 1, 2)


def test_mixed_report_preserves_python_steps_and_native_suite_names():
    from hil_automation.native_results import NativeCaseResult

    report = run_suite(Suite("python", {}, [
        HilTestCase("shared-name", [{"action": "expect_heartbeat"}]),
    ]))
    report.native_results.append(NativeCaseResult("cpp", "shared-name", "passed", 1.25))
    report.passed += 1
    decoded = parse_result(protobuf_report(report))
    assert [case.suite for case in decoded.cases] == ["python", "cpp"]
    assert [case.origin for case in decoded.cases] == [pb.PYTHON, pb.NATIVE]
    assert len(decoded.cases[0].steps) == 1
    assert not decoded.cases[1].steps
    assert not decoded.HasField("native_exit_code")


def test_atomic_binary_replacement_and_failure_cleanup(tmp_path, monkeypatch):
    import pytest
    from hil_automation import reporting

    destination = tmp_path / "result.pb"
    report = run_suite(Suite("binary", {}, []))
    reporting.write_protobuf_report(report, destination)
    before = destination.read_bytes()
    replacement = run_suite(Suite("replacement", {}, []))
    replace = reporting.os.replace

    def inspect(source, target):
        assert source.parent == destination.parent
        assert destination.read_bytes() == before
        assert parse_result(source.read_bytes()).run_id == replacement.run_id
        replace(source, target)

    monkeypatch.setattr(reporting.os, "replace", inspect)
    reporting.write_protobuf_report(replacement, destination)
    assert parse_result(destination.read_bytes()).run_id == replacement.run_id

    def denied(source, target):
        raise PermissionError("replacement denied")

    monkeypatch.setattr(reporting.os, "replace", denied)
    previous = destination.read_bytes()
    with pytest.raises(reporting.ReportError, match="replacement denied"):
        reporting.write_protobuf_report(report, destination)
    assert destination.read_bytes() == previous
    assert list(tmp_path.iterdir()) == [destination]


def test_binary_writer_refuses_unrelated_files_and_symlinks(tmp_path):
    import pytest
    from hil_automation.reporting import ReportError, write_protobuf_report

    report = run_suite(Suite("safe", {}, []))
    unrelated = tmp_path / "suite.yaml"
    unrelated.write_text("suite: existing", encoding="utf-8")
    with pytest.raises(ReportError, match="unrelated or invalid"):
        write_protobuf_report(report, unrelated)
    assert unrelated.read_text() == "suite: existing"
    link = tmp_path / "link.pb"
    link.symlink_to(unrelated)
    with pytest.raises(ReportError, match="symbolic link"):
        write_protobuf_report(report, link)
    assert link.is_symlink()
    assert unrelated.read_text() == "suite: existing"


def test_binary_serialization_failure_does_not_touch_report(tmp_path):
    import pytest
    from hil_automation.reporting import ReportError, write_protobuf_report

    destination = tmp_path / "result.pb"
    report = run_suite(Suite("valid", {}, []))
    write_protobuf_report(report, destination)
    original = destination.read_bytes()
    report.duration_ms = float("nan")
    with pytest.raises(ReportError, match="Cannot serialize Protobuf report"):
        write_protobuf_report(report, destination)
    assert destination.read_bytes() == original
    assert list(tmp_path.iterdir()) == [destination]
