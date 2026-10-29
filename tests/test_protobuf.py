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


def test_binary_round_trip_preserves_message():
    from hil_automation.protobuf import parse_result, serialize_result

    original = report_to_proto(sample_report())
    payload = serialize_result(original)
    assert isinstance(payload, bytes)
    assert parse_result(payload) == original
    assert serialize_result(parse_result(payload)) == payload


def test_binary_decoder_rejects_malformed_wire_format():
    import pytest
    from hil_automation.protobuf import ProtobufError, parse_result

    with pytest.raises(ProtobufError, match="Malformed"):
        parse_result(b"\x80")


def test_application_validation_rejects_defaults_versions_and_bad_fields():
    import pytest
    from hil_automation.protobuf import ProtobufError, parse_result, serialize_result

    with pytest.raises(ProtobufError, match="schema version"):
        parse_result(b"")
    for mutate in [
        lambda message: setattr(message, "schema_version", 2),
        lambda message: setattr(message, "run_id", ""),
        lambda message: message.ClearField("summary"),
        lambda message: setattr(message.summary, "total", 99),
        lambda message: setattr(message.cases[0], "status", 99),
        lambda message: setattr(message.cases[0], "origin", 0),
        lambda message: setattr(message.cases[0], "duration_ms", float("nan")),
    ]:
        message = report_to_proto(sample_report())
        mutate(message)
        with pytest.raises(ProtobufError):
            serialize_result(message)
        with pytest.raises(ProtobufError):
            parse_result(message.SerializeToString())


def test_skipped_cases_and_failure_details_round_trip():
    from hil_automation.protobuf import parse_result, serialize_result

    report = run_suite(Suite("fail-fast", {}, [
        HilTestCase("fails", [{"action": "expect_temperature_below", "limit_c": 0}]),
        HilTestCase("later", [{"action": "expect_heartbeat"}]),
    ]), fail_fast=True)
    decoded = parse_result(serialize_result(report_to_proto(report)))
    assert [case.status for case in decoded.cases] == [pb.FAILED, pb.SKIPPED]
    assert decoded.cases[0].details == report.results[0].details
    assert decoded.cases[0].failure_category == "assertion_failure"
    assert decoded.cases[1].steps[0].status == pb.SKIPPED
    assert decoded.cases[1].duration_ms == 0
    assert (decoded.summary.passed, decoded.summary.failed, decoded.summary.skipped) == (0, 1, 1)


def test_proto_defaults_are_not_application_valid_and_zero_case_runs_are_valid():
    import pytest
    from hil_automation.protobuf import ProtobufError, parse_result, serialize_result

    defaults = pb.RunResult()
    assert defaults.schema_version == defaults.summary.total == 0
    assert not defaults.HasField("summary")
    with pytest.raises(ProtobufError):
        serialize_result(defaults)
    empty = report_to_proto(run_suite(Suite("empty", {}, [])))
    assert parse_result(serialize_result(empty)) == empty


def test_unknown_fields_survive_within_supported_application_version():
    from hil_automation.protobuf import parse_result, serialize_result

    payload = serialize_result(report_to_proto(sample_report()))
    unknown = b"\x98\x06\x07"  # Future field 99, varint 7.
    assert serialize_result(parse_result(payload + unknown)).endswith(unknown)


def test_invalid_application_values_and_wire_payloads():
    import pytest
    from hil_automation.protobuf import ProtobufError, parse_result, serialize_result

    mutations = [
        lambda message: setattr(message.cases[0], "name", " "),
        lambda message: setattr(message.cases[0], "duration_ms", -1),
        lambda message: setattr(message.summary, "duration_ms", float("inf")),
        lambda message: setattr(message.cases[1], "details", ""),
        lambda message: setattr(message.cases[0].steps[0], "index", 3),
        lambda message: setattr(message.cases[0].steps[0], "action", ""),
        lambda message: setattr(message.cases[0].steps[0], "status", pb.DISABLED),
        lambda message: setattr(message.cases[0], "status", pb.DISABLED),
        lambda message: message.cases.add().CopyFrom(message.cases[0]),
        lambda message: setattr(message, "native_exit_code", 1),
    ]
    for mutate in mutations:
        message = report_to_proto(sample_report())
        mutate(message)
        with pytest.raises(ProtobufError):
            parse_result(message.SerializeToString())
    for payload in (None, "text", bytearray(), b"\xff", b"\x80"):
        with pytest.raises(ProtobufError):
            parse_result(payload)
    with pytest.raises(ProtobufError, match="16 MiB"):
        parse_result(b"\x00" * (16 * 1024 * 1024 + 1))
    with pytest.raises(ProtobufError, match="Expected a RunResult"):
        serialize_result(object())
