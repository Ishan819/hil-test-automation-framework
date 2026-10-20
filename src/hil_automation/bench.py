"""Abstraction for the device being tested and a deterministic simulator."""
from dataclasses import dataclass
from typing import Protocol


class Bench(Protocol):
    """Operations any real or simulated HIL bench must implement."""

    def set_voltage(self, voltage: float) -> None: ...

    def read_voltage(self) -> float: ...

    def read_temperature_c(self) -> float: ...

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

    def read_temperature_c(self) -> float:
        return self.temperature_c

    def heartbeat_ok(self) -> bool:
        return self.connected
