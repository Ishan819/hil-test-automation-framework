#pragma once

namespace hil {

// Deterministic software simulation only; no physical hardware I/O.
class SimulatedBench {
public:
    explicit SimulatedBench(double voltage = 0.0, double temperature_c = 28.0,
                            bool connected = true);

    // Inclusive simulation ranges: 0 to 24 V, -40 to 150 degrees Celsius.
    void set_voltage(double voltage);
    void set_temperature(double temperature_c);
    void set_connected(bool connected) noexcept;

    [[nodiscard]] double read_voltage() const noexcept;
    [[nodiscard]] double read_temperature_c() const noexcept;
    [[nodiscard]] bool heartbeat_ok() const noexcept;

private:
    double voltage_ = 0.0;
    double temperature_c_ = 28.0;
    bool connected_ = true;
};

}  // namespace hil
