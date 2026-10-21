"""Abstraction for the device being tested and a deterministic simulator."""
from dataclasses import dataclass
import math
from typing import Protocol


class Bench(Protocol):
    """Operations any real or simulated HIL bench must implement."""

    def set_voltage(self, voltage: float) -> None: ...

    def read_voltage(self) -> float: ...

    def set_temperature(self, temperature_c: float) -> None: ...

    def read_temperature_c(self) -> float: ...

    def set_connected(self, connected: bool) -> None: ...

    def heartbeat_ok(self) -> bool: ...


@dataclass
class SimulatedBench:
    """Stand-in hardware for safe local testing (no physical I/O)."""

    voltage: float = 0.0
    temperature_c: float = 28.0
    connected: bool = True

    def set_voltage(self, voltage: float) -> None:
        if not 0.0 <= voltage <= 24.0:
            raise ValueError("Voltage must be between 0 and 24 V")
        self.voltage = voltage

    def read_voltage(self) -> float:
        return self.voltage

    def set_temperature(self, temperature_c: float) -> None:
        """Set simulated temperature in the inclusive range -40 to 150 °C."""
        if (
            isinstance(temperature_c, bool)
            or not isinstance(temperature_c, (int, float))
            or not -40 <= temperature_c <= 150
            or not math.isfinite(temperature_c)
        ):
            raise ValueError("Temperature must be a finite number between -40 and 150 °C")
        self.temperature_c = float(temperature_c)

    def read_temperature_c(self) -> float:
        return self.temperature_c

    def set_connected(self, connected: bool) -> None:
        """Change the simulated device connection without physical I/O."""
        if not isinstance(connected, bool):
            raise ValueError("Connection state must be true or false")
        self.connected = connected

    def heartbeat_ok(self) -> bool:
        return self.connected
