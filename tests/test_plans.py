from pathlib import Path

import pytest
import yaml

from hil_automation.plans import load_plan


def suite_file(path, name=None):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump({
        "suite": name or path.stem, "bench": {"type": "simulated"},
        "tests": [{"name": "alive", "steps": [{"action": "expect_heartbeat"}]}],
    }))
    return path


def plan_file(tmp_path, entries, **extra):
    path = tmp_path / "plan.yaml"
    path.write_text(yaml.safe_dump({"plan": "daily", "suites": entries, **extra}))
    return path


def test_plan_loads_existing_suites_in_declared_order(tmp_path):
    first = suite_file(tmp_path / "one.yaml")
    second = suite_file(tmp_path / "two.yaml")
    plan = load_plan(plan_file(tmp_path, ["two.yaml", "one.yaml"]))
    assert plan.name == "daily"
    assert [entry.path for entry in plan.suites] == [second, first]
    assert [entry.suite.name for entry in plan.suites] == ["two", "one"]


@pytest.mark.parametrize("entry", [None, True, 1, {}, [], "", " missing ", "/absolute.yaml", "missing.yaml"])
def test_invalid_suite_references_are_rejected(tmp_path, entry):
    with pytest.raises(ValueError, match="suite paths|relative file|does not exist"):
        load_plan(plan_file(tmp_path, [entry]))


def test_duplicate_resolved_paths_are_rejected(tmp_path):
    suite_file(tmp_path / "one.yaml")
    with pytest.raises(ValueError, match="Duplicate suite"):
        load_plan(plan_file(tmp_path, ["one.yaml", "./one.yaml"]))


def test_invalid_referenced_suite_is_rejected_before_execution(tmp_path):
    (tmp_path / "invalid.yaml").write_text("suite: incomplete")
    with pytest.raises(ValueError, match="Invalid plan suite"):
        load_plan(plan_file(tmp_path, ["invalid.yaml"]))
