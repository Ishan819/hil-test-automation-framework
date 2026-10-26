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


def test_failure_skip_and_disabled_outcomes(tmp_path):
    from hil_automation.native_results import parse_gtest_xml

    path = tmp_path / "outcomes.xml"
    path.write_text("""<testsuite name="Cases">
      <testcase name="Bad" time="0.002">
        <failure message="expected &lt; 5"><![CDATA[file.cpp:12 expected < 5]]></failure>
        <failure message="second failure"/>
      </testcase>
      <testcase name="Skip" status="run" result="skipped" time="0">
        <skipped message="not ready">not ready</skipped>
      </testcase>
      <testcase name="DISABLED_Later" status="notrun" result="suppressed"/>
      <testcase name="DISABLED_ExplicitlyRun" status="run" result="completed" time="0.1"/>
    </testsuite>""")
    cases = parse_gtest_xml(path)
    assert [case.status for case in cases] == ["failed", "skipped", "disabled", "passed"]
    assert cases[0].details == "expected < 5\nfile.cpp:12 expected < 5\nsecond failure"
    assert cases[1].details == "not ready"
    assert cases[2].duration_ms == 0


def test_invalid_xml_and_missing_information(tmp_path):
    import pytest
    from hil_automation.native_results import NativeResultError, parse_gtest_xml

    invalid = [
        "<testsuites>", "<unknown/>",
        '<testsuite><testcase name="MissingSuite" time="0"/></testsuite>',
        '<testsuite name="Suite"><testcase time="0"/></testsuite>',
        '<testsuite name="Suite"><testcase name="MissingTime"/></testsuite>',
        *[f'<testsuite name="Suite"><testcase name="Bad" time="{value}"/></testsuite>'
          for value in ("-1", "nan", "inf", "1e999", "invalid")],
        '<testsuite name="Suite"><testcase name="Bad" time="0" result="unknown"/></testsuite>',
        '<testsuite name="Suite"><testcase name="Bad" time="0" status="unknown"/></testsuite>',
        '<testsuite name="Suite"><testcase name="Bad" time="0" result="suppressed"/></testsuite>',
        '<testsuite name="Suite"><testcase name="Same" time="0"/><testcase name="Same" time="0"/></testsuite>',
    ]
    path = tmp_path / "invalid.xml"
    for content in invalid:
        path.write_text(content)
        with pytest.raises(NativeResultError):
            parse_gtest_xml(path)
    with pytest.raises(NativeResultError, match="Cannot read GoogleTest XML"):
        parse_gtest_xml(tmp_path / "missing.xml")
