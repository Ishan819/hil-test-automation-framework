from pathlib import Path

import pytest
import yaml

from hil_automation.config import MAX_RETRIES, TestCase as HilTestCase, load_suite


def retry_suite(tmp_path, **fields):
    test = {"name": "retry-case", "steps": [{"action": "expect_heartbeat"}], **fields}
    path = tmp_path / "retry.yaml"
    path.write_text(yaml.safe_dump({"suite": "retry", "bench": {"type": "simulated"}, "tests": [test]}))
    return path


def test_retry_policy_is_optional_and_explicit(tmp_path):
    assert load_suite(retry_suite(tmp_path)).tests[0].retries == 0
    assert load_suite(retry_suite(tmp_path, retries=2)).tests[0].retries == 2
    assert MAX_RETRIES == 3


@pytest.mark.parametrize("value", [-1, 4, True, False, None, 1.0, "1", [], {}])
def test_invalid_retry_counts_are_rejected(tmp_path, value):
    with pytest.raises(ValueError, match="retries must be an integer between 0 and 3"):
        load_suite(retry_suite(tmp_path, retries=value))
    with pytest.raises(ValueError, match="retries"):
        HilTestCase("direct", [{"action": "expect_heartbeat"}], retries=value)


@pytest.mark.parametrize("value", range(MAX_RETRIES + 1))
def test_each_supported_retry_count_loads(tmp_path, value):
    assert load_suite(retry_suite(tmp_path, retries=value)).tests[0].retries == value


@pytest.mark.parametrize("scenario", ["smoke", "recovery", "faults", "failure_demo"])
def test_existing_scenarios_have_retries_disabled(scenario):
    path = Path(__file__).resolve().parents[1] / "scenarios" / f"{scenario}.yaml"
    assert all(case.retries == 0 for case in load_suite(path).tests)


def test_retry_and_tags_configuration_can_coexist(tmp_path):
    case = load_suite(retry_suite(tmp_path, retries=1, tags=["thermal"])).tests[0]
    assert case.retries == 1
    assert case.tags == ("thermal",)


@pytest.mark.parametrize("value", [float("nan"), float("inf"), -float("inf")])
def test_nonfinite_assertion_configuration_is_rejected_before_retry(tmp_path, value):
    path = retry_suite(tmp_path, retries=3)
    payload = yaml.safe_load(path.read_text())
    payload["tests"][0]["steps"] = [{"action": "expect_temperature_below", "limit_c": value}]
    path.write_text(yaml.safe_dump(payload))
    with pytest.raises(ValueError, match="must be a number"):
        load_suite(path)
