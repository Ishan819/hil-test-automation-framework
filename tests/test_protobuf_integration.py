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
