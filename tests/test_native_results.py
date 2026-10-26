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


def test_multiple_google_suites_preserve_names_order_and_millisecond_units(tmp_path):
    from hil_automation.native_results import parse_gtest_xml

    path = tmp_path / "suites.xml"
    path.write_text("""<testsuites tests="3">
      <testsuite name="Voltage">
        <testcase name="Boundary/0" classname="Voltage" time="0"/>
        <testcase name="Nominal" classname="Voltage" time="1.25"/>
      </testsuite>
      <testsuite name="TypedSuite/0">
        <testcase name="Reads" classname="TypedSuite/0" type_param="double" time="1e-3"/>
      </testsuite>
    </testsuites>""")
    assert parse_gtest_xml(path) == [
        NativeCaseResult("Voltage", "Boundary/0", "passed", 0),
        NativeCaseResult("Voltage", "Nominal", "passed", 1250),
        NativeCaseResult("TypedSuite/0", "Reads", "passed", 1),
    ]


def test_empty_gtest_report_is_valid(tmp_path):
    from hil_automation.native_results import parse_gtest_xml

    path = tmp_path / "empty.xml"
    path.write_text('<testsuites tests="0"/>')
    assert parse_gtest_xml(path) == []


def test_nested_suites_and_optional_properties_do_not_duplicate_cases(tmp_path):
    from hil_automation.native_results import parse_gtest_xml

    path = tmp_path / "nested.xml"
    path.write_text("""<testsuites>
      <testsuite name="group">
        <properties><property name="key" value="value"/></properties>
        <testsuite name="Inner"><testcase name="Works" time="0.002">
          <properties><property name="value" value="ok"/></properties>
        </testcase></testsuite>
      </testsuite>
    </testsuites>""")
    assert parse_gtest_xml(path) == [NativeCaseResult("Inner", "Works", "passed", 2)]
