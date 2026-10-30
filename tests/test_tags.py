from pathlib import Path

import pytest
import yaml

from hil_automation.config import load_suite


def tagged_suite(tmp_path, tags=None):
    test = {"name": "alive", "steps": [{"action": "expect_heartbeat"}]}
    if tags is not None:
        test["tags"] = tags
    path = tmp_path / "tags.yaml"
    path.write_text(yaml.safe_dump({"suite": "tags", "bench": {"type": "simulated"}, "tests": [test]}))
    return path


def test_optional_case_tags(tmp_path):
    assert load_suite(tagged_suite(tmp_path, ["smoke", "connection"])).tests[0].tags == ("smoke", "connection")
    assert load_suite(tagged_suite(tmp_path)).tests[0].tags == ()


@pytest.mark.parametrize("tags", ["smoke", 1, True, {}, ["", "ok"], [" smoke"], ["smoke", "smoke"], [1], [False]])
def test_invalid_tag_definitions(tmp_path, tags):
    with pytest.raises(ValueError, match="tags"):
        load_suite(tagged_suite(tmp_path, tags))


@pytest.mark.parametrize("tags", [[], ["thermal"], ["Smoke", "smoke"], ["thermal", "regression", "connection"]])
def test_valid_tag_lists_preserve_order_and_case(tmp_path, tags):
    assert load_suite(tagged_suite(tmp_path, tags)).tests[0].tags == tuple(tags)


def test_explicit_null_tags_are_not_treated_as_missing(tmp_path):
    path = tagged_suite(tmp_path)
    payload = yaml.safe_load(path.read_text())
    payload["tests"][0]["tags"] = None
    path.write_text(yaml.safe_dump(payload))
    with pytest.raises(ValueError, match="tags must be a list"):
        load_suite(path)


@pytest.mark.parametrize("scenario", ["smoke", "recovery", "faults", "failure_demo"])
def test_existing_suites_remain_untagged_and_valid(scenario):
    path = Path(__file__).resolve().parents[1] / "scenarios" / f"{scenario}.yaml"
    assert all(case.tags == () for case in load_suite(path).tests)


def test_cli_tag_selects_only_matches(tmp_path):
    import json
    import subprocess
    import sys

    path = tagged_suite(tmp_path, ["smoke"])
    report = tmp_path / "tagged.json"
    finished = subprocess.run(
        [sys.executable, "-m", "hil_automation.cli", str(path), "--tag", "smoke", "--report", str(report)],
        capture_output=True, text=True,
    )
    assert finished.returncode == 0, finished.stderr
    assert [case["name"] for case in json.loads(report.read_text())["results"]] == ["alive"]
