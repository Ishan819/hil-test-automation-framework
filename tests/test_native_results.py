from dataclasses import asdict

from hil_automation.native_results import NativeCaseResult


def test_native_case_model_serializes_with_existing_result_conventions():
    case = NativeCaseResult("Thermal", "Cools", "passed", 12.5)
    assert asdict(case) == {
        "suite": "Thermal", "name": "Cools", "status": "passed",
        "duration_ms": 12.5, "details": "",
    }


def test_parser_reads_single_suite(tmp_path):
    from hil_automation.native_results import parse_gtest_xml

    path = tmp_path / "native.xml"
    path.write_text('<testsuite name="Voltage"><testcase name="Nominal" time="0.0125"/></testsuite>')
    assert parse_gtest_xml(path) == [
        NativeCaseResult("Voltage", "Nominal", "passed", 12.5),
    ]
