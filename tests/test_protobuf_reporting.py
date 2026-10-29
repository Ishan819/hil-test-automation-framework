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
