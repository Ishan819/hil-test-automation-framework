#include "hil/simulated_bench.hpp"

#include <cmath>
#include <stdexcept>

namespace hil {

SimulatedBench::SimulatedBench(double voltage, double temperature_c, bool connected) {
    set_voltage(voltage);
    set_temperature(temperature_c);
    set_connected(connected);
}

void SimulatedBench::set_voltage(double voltage) {
    if (!std::isfinite(voltage) || voltage < 0.0 || voltage > 24.0) {
        throw std::invalid_argument("Voltage must be a finite number between 0 and 24 V");
    }
    voltage_ = voltage;
}

void SimulatedBench::set_temperature(double temperature_c) {
    if (!std::isfinite(temperature_c) || temperature_c < -40.0 || temperature_c > 150.0) {
        throw std::invalid_argument(
            "Temperature must be a finite number between -40 and 150 degrees C");
    }
    temperature_c_ = temperature_c;
}

void SimulatedBench::set_connected(bool connected) noexcept {
    connected_ = connected;
}

double SimulatedBench::read_voltage() const noexcept {
    return voltage_;
}

double SimulatedBench::read_temperature_c() const noexcept {
    return temperature_c_;
}

bool SimulatedBench::heartbeat_ok() const noexcept {
    return connected_;
}

}  // namespace hil
