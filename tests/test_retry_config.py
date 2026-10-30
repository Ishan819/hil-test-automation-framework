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
