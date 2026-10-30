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
