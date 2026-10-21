import pytest

from hil_automation.bench import SimulatedBench


@pytest.mark.parametrize("value", [-40, -39.9, 0, 28.5, 149.9, 150])
def test_set_temperature(value):
    bench = SimulatedBench()
    bench.set_temperature(value)
    assert bench.read_temperature_c() == value


@pytest.mark.parametrize("value", [-40.1, 150.1, True, False, float("nan"),
                                  float("inf"), -float("inf"), "28", None, [], 10**1000])
def test_invalid_temperature_preserves_state(value):
    bench = SimulatedBench()
    with pytest.raises(ValueError, match="Temperature must be a finite number"):
        bench.set_temperature(value)
    assert bench.read_temperature_c() == 28


def test_disconnect_and_reconnect():
    bench = SimulatedBench()
    bench.set_connected(False)
    assert bench.heartbeat_ok() is False
    bench.set_connected(True)
    assert bench.heartbeat_ok() is True


@pytest.mark.parametrize("value", [0, 1, -1, 1.0, "true", "false", None, [], {}])
def test_invalid_connection_preserves_state(value):
    bench = SimulatedBench()
    with pytest.raises(ValueError, match="Connection state must be true or false"):
        bench.set_connected(value)
    assert bench.heartbeat_ok() is True


@pytest.mark.parametrize("value", [-40, 28.5, 150])
def test_initial_temperature(value):
    assert SimulatedBench(temperature_c=value).read_temperature_c() == value


@pytest.mark.parametrize("value", [True, False, "28", None, float("nan"),
                                  float("inf"), -float("inf"), -41, 151, 10**1000])
def test_invalid_initial_temperature(value):
    with pytest.raises(ValueError, match="Temperature must be a finite number"):
        SimulatedBench(temperature_c=value)
