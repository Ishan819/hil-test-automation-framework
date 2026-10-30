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
