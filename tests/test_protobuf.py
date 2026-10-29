from hil_automation.config import Suite, TestCase as HilTestCase
from hil_automation.proto import hil_results_pb2 as pb
from hil_automation.protobuf import report_to_proto
from hil_automation.runner import run_suite


def sample_report():
    return run_suite(Suite("protobuf-tests", {}, [
        HilTestCase("healthy", [{"action": "expect_heartbeat"}]),
        HilTestCase("hot", [
            {"action": "set_temperature", "value": 95},
            {"action": "expect_temperature_below", "limit_c": 75},
            {"action": "expect_heartbeat"},
        ]),
    ]))


def test_python_mapping_preserves_identifiers_outcomes_and_steps():
    report = sample_report()
    message = report_to_proto(report)
    assert (message.schema_version, message.run_id, message.suite) == (1, report.run_id, report.suite)
    assert (message.summary.total, message.summary.passed, message.summary.failed) == (2, 1, 1)
    assert [case.status for case in message.cases] == [pb.PASSED, pb.FAILED]
    assert all(case.origin == pb.PYTHON for case in message.cases)
    assert message.cases[1].details == report.results[1].details
    assert message.cases[1].failure_category == "assertion_failure"
    assert [step.status for step in message.cases[1].steps] == [pb.PASSED, pb.FAILED, pb.SKIPPED]
    assert message.summary.duration_ms == report.duration_ms
