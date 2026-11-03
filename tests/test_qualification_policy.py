from hil_automation.qualification_policy import QualificationPolicy, load_policy


def test_default_policy_requires_all_cases_to_pass_without_retries(tmp_path):
    path = tmp_path / "policy.yaml"
    path.write_text("{}")
    assert load_policy(path) == QualificationPolicy(100.0, 0, False, False)


def test_explicit_policy_criteria_are_loaded(tmp_path):
    path = tmp_path / "policy.yaml"
    path.write_text("min_pass_percentage: 90\nmax_failed_cases: 2\nallow_skipped: true\nallow_recovered: true\n")
    assert load_policy(path) == QualificationPolicy(90, 2, True, True)
