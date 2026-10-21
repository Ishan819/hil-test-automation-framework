import pytest

from hil_automation.config import load_suite


def write_suite(tmp_path, step, bench="{type: simulated}"):
    path = tmp_path / "suite.yaml"
    path.write_text(
        f"suite: validation\nbench: {bench}\ntests:\n"
        f"  - name: control\n    steps:\n      - {step}\n",
        encoding="utf-8",
    )
    return path


@pytest.mark.parametrize("value", ["-40", "0", "28.5", "150"])
def test_temperature_action_loads(tmp_path, value):
    suite = load_suite(write_suite(tmp_path, f"{{action: set_temperature, value: {value}}}"))
    assert suite.tests[0].steps[0]["value"] == float(value)


@pytest.mark.parametrize("field", ["", ", value: true", ", value: false",
                                 ", value: '28'", ", value: null", ", value: []",
                                 ", value: {}", ", value: .nan", ", value: .inf",
                                 ", value: -.inf", ", value: -40.1", ", value: 150.1"])
def test_invalid_temperature_action(tmp_path, field):
    with pytest.raises(ValueError, match="must be a number|Temperature must be"):
        load_suite(write_suite(tmp_path, f"{{action: set_temperature{field}}}"))


@pytest.mark.parametrize("value, expected", [("true", True), ("false", False)])
def test_connection_action_loads(tmp_path, value, expected):
    suite = load_suite(write_suite(tmp_path, f"{{action: set_connection, connected: {value}}}"))
    assert suite.tests[0].steps[0]["connected"] is expected


@pytest.mark.parametrize("field", ["", ", connected: 0", ", connected: 1",
                                 ", connected: 1.0", ", connected: 'true'",
                                 ", connected: 'false'", ", connected: null",
                                 ", connected: []", ", connected: {}",
                                 ", connected: .nan"])
def test_invalid_connection_action(tmp_path, field):
    with pytest.raises(ValueError, match="set_connection.connected must be true or false"):
        load_suite(write_suite(tmp_path, f"{{action: set_connection{field}}}"))
