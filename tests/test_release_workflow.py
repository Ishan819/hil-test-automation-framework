"""Exercise duplicate suite names, retry resets and publication in one CLI workflow."""
import json
import subprocess
import sys
from pathlib import Path

import pytest
import yaml


@pytest.mark.parametrize("format", ["json", "junit", "protobuf"])
@pytest.mark.parametrize("fault", [False, True])
def test_parallel_release_preserves_isolation_and_previous_evidence(tmp_path, format, fault):
    for index in (1, 2):
        initial = {"action": "expect_voltage", "value": index, "tolerance": 0}
        steps = [initial, {"action": "set_voltage", "value": 12}]
        if fault:
            steps += [{"action": "set_connection", "connected": False}, {"action": "expect_heartbeat"}]
        (tmp_path / f"{index}.yaml").write_text(yaml.safe_dump({
            "suite": "same-name", "bench": {"type": "simulated", "initial_voltage": index},
            "tests": [{"name": "mutate", "retries": 1, "steps": steps},
                      {"name": "fresh", "steps": [initial, {"action": "expect_heartbeat"}]}],
        }))
    plan = tmp_path / "plan.yaml"
    plan.write_text("plan: release\nsuites: [1.yaml, 2.yaml]\nworkers: 2\n")
    policy = tmp_path / "policy.yaml"
    policy.write_text("{}")
    output = tmp_path / "reports"
    previous = {}
    for _ in range(2):
        result = subprocess.run([sys.executable, "-m", "hil_automation.cli", "--plan", str(plan),
                                 "--qualification-policy", str(policy), "--report-dir", str(output),
                                 "--report-format", format], capture_output=True, text=True, cwd=tmp_path)
        assert result.returncode == int(fault), result.stderr
        assert not result.stderr
        assert all(path.read_bytes() == content for path, content in previous.items())
        manifests = list(output.glob("*/batch.json"))
        current = next(path for path in manifests if path not in previous)
        batch = json.loads(current.read_text())
        decision = json.loads(current.with_name("qualification.json").read_text())
        assert decision["qualified"] is (not fault) and decision["complete_evidence"]
        assert decision["observed"]["total_cases"] == 4
        assert decision["observed"]["failed_cases"] == 2 * fault
        assert len({s["report_file"] for s in batch["suites"]}) == 2
        for suite in batch["suites"]:
            mutate, fresh = suite["report"]["results"]
            assert fresh["status"] == "passed"
            assert mutate["retry_count"] == int(fault)
            assert all(a["steps"][0]["status"] == "passed" for a in mutate["attempts"])
            assert (current.parent / suite["report_file"]).is_file()
        previous = {path: path.read_bytes() for path in output.rglob("*") if path.is_file()}
    assert len(list(output.glob("*/batch.json"))) == 2
