import pytest

from hil_automation.config import Suite, TestCase as HilTestCase
from hil_automation.proto import hil_results_pb2 as pb
from hil_automation.protobuf import ProtobufError, parse_result, report_to_proto
from hil_automation.qualification import evaluate_qualification
from hil_automation.qualification_policy import QualificationPolicy
from hil_automation.reporting import junit_xml, protobuf_report
from hil_automation.runner import run_suite


def evidence():
    suite = Suite("evidence", {}, [HilTestCase("healthy", [{"action": "expect_heartbeat"}])])
    return suite, run_suite(suite)


@pytest.mark.parametrize("status", [pb.FAILED, pb.SKIPPED])
def test_contradictory_passing_binary_evidence_is_rejected(status):
    _, report = evidence()
    message = report_to_proto(report)
    message.cases[0].steps[0].status = status
    message.cases[0].steps[0].details = "SECRET_VALUE"
    with pytest.raises(ProtobufError, match="Passed case contains unsuccessful steps") as error:
        parse_result(message.SerializeToString())
    assert "SECRET_VALUE" not in str(error.value)


@pytest.mark.parametrize("format", ["json", "junit", "protobuf"])
def test_serialized_reports_cannot_replace_validated_execution_evidence(format):
    suite, report = evidence()
    payload = {"json": report.to_dict, "junit": lambda: junit_xml(report),
               "protobuf": lambda: parse_result(protobuf_report(report))}[format]()
    result = evaluate_qualification(payload, QualificationPolicy(0, 100, True, True), expected=suite)
    assert not result.qualified and not result.complete
