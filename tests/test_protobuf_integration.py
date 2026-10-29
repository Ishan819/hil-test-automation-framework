import subprocess

import pytest

from hil_automation.proto import hil_results_pb2 as pb
from hil_automation.protobuf import parse_result


pytestmark = pytest.mark.protobuf_integration


@pytest.mark.parametrize("fault", [False, True])
def test_cpp_produces_real_bench_results_python_validates(
    compiled_proto_binary, tmp_path, fault,
):
    output = tmp_path / "native.pb"
    command = [str(compiled_proto_binary), "produce", str(output), "cpp-to-python"]
    if fault:
        command.append("--fault")
    finished = subprocess.run(command, capture_output=True, text=True)
    assert finished.returncode == 0, finished.stderr
    result = parse_result(output.read_bytes())
    assert result.schema_version == 1
    assert result.run_id == "cpp-to-python"
    assert result.suite == "cpp-simulated-bench"
    assert [case.name for case in result.cases] == [
        "voltage_is_five_volts", "temperature_below_75", "device_heartbeat",
    ]
    assert all(case.origin == pb.NATIVE for case in result.cases)
    assert all(case.status == (pb.FAILED if fault else pb.PASSED) for case in result.cases)
    assert result.summary.total == 3
    assert result.summary.failed == (3 if fault else 0)
    assert result.summary.passed == (0 if fault else 3)
    assert ("95.000000" if fault else "28.000000") in result.cases[1].details
    if fault:
        assert result.cases[2].failure_category == "simulated_connection_failure"
    assert result.summary.duration_ms >= 0


@pytest.mark.parametrize("fail_fast", [False, True])
def test_python_report_survives_real_cpp_validation_and_roundtrip(
    compiled_proto_binary, tmp_path, fail_fast,
):
    from hil_automation.config import Suite, TestCase as HilTestCase
    from hil_automation.protobuf import report_to_proto, serialize_result
    from hil_automation.runner import run_suite

    report = run_suite(Suite("suite <&π", {}, [
        HilTestCase("hot α", [
            {"action": "expect_temperature_below", "limit_c": 0},
            {"action": "expect_heartbeat"},
        ]),
        HilTestCase("healthy", [{"action": "expect_heartbeat"}]),
    ]), fail_fast=fail_fast)
    message = report_to_proto(report)
    source, output = tmp_path / "python.pb", tmp_path / "cpp.pb"
    source.write_bytes(serialize_result(message))
    verified = subprocess.run(
        [str(compiled_proto_binary), "verify", str(source)], capture_output=True, text=True,
    )
    assert verified.returncode == 0, verified.stderr
    assert f"run_id={report.run_id}" in verified.stdout
    assert "cases=2" in verified.stdout
    exchanged = subprocess.run(
        [str(compiled_proto_binary), "roundtrip", str(source), str(output)],
        capture_output=True, text=True,
    )
    assert exchanged.returncode == 0, exchanged.stderr
    assert parse_result(output.read_bytes()) == message


@pytest.mark.parametrize("kind", ["malformed", "defaults", "version", "counts", "duration", "status"])
def test_cpp_rejects_corrupt_or_invalid_python_payloads(
    compiled_proto_binary, tmp_path, kind,
):
    from hil_automation.config import Suite
    from hil_automation.protobuf import report_to_proto
    from hil_automation.runner import run_suite

    message = report_to_proto(run_suite(Suite("invalid", {}, [])))
    if kind == "version":
        message.schema_version = 2
    elif kind == "counts":
        message.summary.total = 1
    elif kind == "duration":
        message.summary.duration_ms = float("nan")
    elif kind == "status":
        message.cases.add(suite="invalid", name="bad", origin=pb.PYTHON, status=99)
        message.summary.total = 1
    payload = b"\x80" if kind == "malformed" else b"" if kind == "defaults" else message.SerializeToString()
    source, output = tmp_path / "bad.pb", tmp_path / "unused.pb"
    source.write_bytes(payload)
    finished = subprocess.run(
        [str(compiled_proto_binary), "roundtrip", str(source), str(output)],
        capture_output=True, text=True,
    )
    assert finished.returncode == 2
    assert "Error:" in finished.stderr
    assert not output.exists()


def test_cpp_preserves_unknown_fields_and_refuses_output_overwrite(compiled_proto_binary, tmp_path):
    from hil_automation.config import Suite
    from hil_automation.protobuf import report_to_proto, serialize_result
    from hil_automation.runner import run_suite

    message = report_to_proto(run_suite(Suite("future-compatible", {}, [])))
    payload = serialize_result(message) + b"\x98\x06\x07"
    source, output = tmp_path / "source.pb", tmp_path / "output.pb"
    source.write_bytes(payload)
    command = [str(compiled_proto_binary), "roundtrip", str(source), str(output)]
    finished = subprocess.run(command, capture_output=True, text=True)
    assert finished.returncode == 0, finished.stderr
    assert parse_result(output.read_bytes()) == parse_result(payload)
    previous = output.read_bytes()
    assert subprocess.run(command, capture_output=True).returncode == 2
    assert output.read_bytes() == previous
