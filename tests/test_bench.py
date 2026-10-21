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
