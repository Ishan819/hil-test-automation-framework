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


@pytest.mark.parametrize("payload", [
    None, [], "plan", True, {"plan": "", "suites": []},
    {"plan": "daily", "suites": []}, {"plan": "daily", "suites": "one.yaml"},
    {"plan": 3, "suites": ["one.yaml"]}, {"plan": "daily", "suites": ["one.yaml"], "parallel": True},
])
def test_empty_and_unsupported_plan_shapes(tmp_path, payload):
    path = tmp_path / "invalid.yaml"
    path.write_text(yaml.safe_dump(payload))
    with pytest.raises(ValueError):
        load_plan(path)


def test_malformed_plan_yaml_has_context(tmp_path):
    path = tmp_path / "malformed.yaml"
    path.write_text("plan: [")
    with pytest.raises(ValueError, match="Invalid plan YAML"):
        load_plan(path)


def test_relative_paths_resolve_against_plan_not_current_directory(tmp_path, monkeypatch):
    suite = suite_file(tmp_path / "suite.yaml")
    directory = tmp_path / "plans"
    directory.mkdir()
    plan = plan_file(directory, ["../suite.yaml"])
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)
    assert load_plan(plan).suites[0].path == suite


def test_directory_and_symlink_duplicate_paths_are_rejected(tmp_path):
    suite = suite_file(tmp_path / "one.yaml")
    alias = tmp_path / "alias.yaml"
    alias.symlink_to(suite)
    with pytest.raises(ValueError, match="Duplicate suite"):
        load_plan(plan_file(tmp_path, ["one.yaml", "alias.yaml"]))
    with pytest.raises(ValueError, match="does not exist"):
        load_plan(plan_file(tmp_path, ["."]))


def test_distinct_suite_files_may_share_a_display_name(tmp_path):
    suite_file(tmp_path / "one.yaml", "same-name")
    suite_file(tmp_path / "two.yaml", "same-name")
    assert len(load_plan(plan_file(tmp_path, ["one.yaml", "two.yaml"])).suites) == 2
