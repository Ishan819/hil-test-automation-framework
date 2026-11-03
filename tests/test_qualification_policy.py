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


@pytest.mark.parametrize("percentage", [0, 0.5, 99.9, 100])
@pytest.mark.parametrize("limit", [0, 1, 1000])
def test_policy_numeric_boundaries_and_partial_defaults(tmp_path, percentage, limit):
    path = tmp_path / "limits.yaml"
    path.write_text(f"min_pass_percentage: {percentage}\nmax_failed_cases: {limit}\n")
    policy = load_policy(path)
    assert policy.min_pass_percentage == percentage
    assert policy.max_failed_cases == limit
    assert policy.allow_skipped is False and policy.allow_recovered is False


@pytest.mark.parametrize("value", [-0.1, 100.1, float("inf"), -float("inf"), "90", None, [], {}, 10**400])
def test_invalid_percentages_in_yaml_and_direct_model(tmp_path, value):
    import yaml

    with pytest.raises(ValueError, match="min_pass_percentage"):
        QualificationPolicy(min_pass_percentage=value)
    path = tmp_path / "limits.yaml"
    path.write_text(yaml.safe_dump({"min_pass_percentage": value}))
    with pytest.raises(ValueError, match="min_pass_percentage"):
        load_policy(path)


@pytest.mark.parametrize("value", [False, 1.0, "1", None, [], {}])
def test_failure_limit_requires_an_integer(value):
    with pytest.raises(ValueError, match="max_failed_cases"):
        QualificationPolicy(max_failed_cases=value)


@pytest.mark.parametrize("text", ["", "null", "[]", "policy", "true", "1: true", "? [a, b]\n: true",
                                       "!!python/object/apply:os.getcwd []", "---\n{}\n---\n{}"])
def test_non_mapping_unsupported_and_multiple_yaml_documents(tmp_path, text):
    path = tmp_path / "shape.yaml"
    path.write_text(text)
    with pytest.raises(ValueError):
        load_policy(path)


def test_invalid_encoding_and_missing_policy_are_not_defaults(tmp_path):
    path = tmp_path / "invalid.yaml"
    path.write_bytes(b"\xff")
    with pytest.raises(ValueError, match="Invalid qualification policy YAML"):
        load_policy(path)
    with pytest.raises(OSError):
        load_policy(tmp_path / "missing.yaml")
