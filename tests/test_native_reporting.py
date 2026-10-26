import json

from hil_automation.native import run_native_tests
from hil_automation.reporting import native_report, write_json_report


def test_native_cases_extend_json_without_changing_python_results(gtest_executable, tmp_path):
    binary = gtest_executable("""<testsuite name="Voltage">
      <testcase name="Nominal" time="0.002"/>
    </testsuite>""")
    result = run_native_tests(binary, capture_xml=True)
    report = native_report(result)
    path = tmp_path / "native.json"
    write_json_report(report, path)
    data = json.loads(path.read_text())
    assert data["schema_version"] == "1.0"
    assert data["results"] == []
    assert data["native_results"] == [{
        "suite": "Voltage", "name": "Nominal", "status": "passed", "duration_ms": 2,
        "details": "",
    }]
    assert (data["passed"], data["failed"], data["native_exit_code"]) == (1, 0, 0)
    assert data["statistics"]["total_cases"] == 1
