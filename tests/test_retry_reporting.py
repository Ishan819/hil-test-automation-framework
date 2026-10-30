import json
from xml.etree import ElementTree as ET

from hil_automation.config import Suite, TestCase as HilTestCase
from hil_automation.proto import hil_results_pb2 as pb
from hil_automation.protobuf import parse_result
from hil_automation.reporting import protobuf_report, write_json_report, write_junit_report
from hil_automation.runner import run_suite


def test_attempt_history_is_preserved_across_supported_report_fields(tmp_path):
    report = run_suite(Suite("retry-report", {}, [
        HilTestCase("thermal", [{"action": "expect_temperature_below", "limit_c": 0}], retries=1),
    ]))
    output = tmp_path / "attempts.json"
    write_json_report(report, output)
    data = json.loads(output.read_text())
    assert data["retry_summary"] == {"total_attempts": 2, "retries": 1, "passed_after_retry": 0}
    assert len(data["results"][0]["attempts"]) == 2
    assert data["statistics"]["failed_steps"] == 2
    assert data["action_statistics"]["expect_temperature_below"]["executed"] == 2

    xml = tmp_path / "attempts.xml"
    write_junit_report(report, xml)
    root = ET.parse(xml).getroot()
    assert root.get("tests") == root.get("failures") == "1"
    history = json.loads(root.find("testcase/system-out").text)
    assert history["retry_count"] == 1
    assert [attempt["status"] for attempt in history["attempts"]] == ["failed", "failed"]

    message = parse_result(protobuf_report(report))
    assert message.cases[0].status == pb.FAILED
    history = json.loads(message.cases[0].details.split("\nRetry history: ", 1)[1])
    assert len(history["attempts"]) == 2
    assert "28.0" in history["attempts"][0]["details"]
    assert message.summary.failed == 1
    assert len(message.cases[0].steps) == 1
