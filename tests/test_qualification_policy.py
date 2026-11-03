from hil_automation.qualification_policy import QualificationPolicy, load_policy


def test_default_policy_requires_all_cases_to_pass_without_retries(tmp_path):
    path = tmp_path / "policy.yaml"
    path.write_text("{}")
    assert load_policy(path) == QualificationPolicy(100.0, 0, False, False)


def test_explicit_policy_criteria_are_loaded(tmp_path):
    path = tmp_path / "policy.yaml"
    path.write_text("min_pass_percentage: 90\nmax_failed_cases: 2\nallow_skipped: true\nallow_recovered: true\n")
    assert load_policy(path) == QualificationPolicy(90, 2, True, True)


import pytest


@pytest.mark.parametrize("criteria, message", [
    ({"min_pass_percentage": True}, "min_pass_percentage must be a finite number"),
    ({"min_pass_percentage": float("nan")}, "min_pass_percentage must be a finite number"),
    ({"max_failed_cases": -1}, "max_failed_cases must be a non-negative integer"),
    ({"max_failed_cases": True}, "max_failed_cases must be a non-negative integer"),
    ({"allow_skipped": "false"}, "allow_skipped must be true or false"),
    ({"allow_recovered": 1}, "allow_recovered must be true or false"),
])
def test_invalid_policy_model_values_are_rejected(criteria, message):
    with pytest.raises(ValueError, match=message):
        QualificationPolicy(**criteria)


@pytest.mark.parametrize("text, message", [
    ("min_pass_percentage: [", "Invalid qualification policy YAML"),
    ("unknown: true", "Unsupported qualification policy fields"),
    ("allow_skipped: false\nallow_skipped: true", "Duplicate qualification policy field"),
])
def test_invalid_yaml_policy_is_rejected(tmp_path, text, message):
    path = tmp_path / "invalid.yaml"
    path.write_text(text)
    with pytest.raises(ValueError, match=message):
        load_policy(path)
