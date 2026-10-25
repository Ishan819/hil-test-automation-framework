#include "hil/simulated_bench.hpp"

#include <gtest/gtest.h>

#include <limits>
#include <stdexcept>

namespace {

using hil::SimulatedBench;

TEST(SimulatedBenchTest, StartsWithSafeDefaults) {
    const SimulatedBench bench;
    EXPECT_DOUBLE_EQ(bench.read_voltage(), 0.0);
    EXPECT_DOUBLE_EQ(bench.read_temperature_c(), 28.0);
    EXPECT_TRUE(bench.heartbeat_ok());
}

TEST(SimulatedBenchTest, AcceptsVoltageIncludingBoundaries) {
    SimulatedBench bench;
    for (double value : {0.0, 3.3, 12.0, 24.0}) {
        bench.set_voltage(value);
        EXPECT_DOUBLE_EQ(bench.read_voltage(), value);
    }
}

TEST(SimulatedBenchTest, RejectsInvalidVoltageWithoutChangingState) {
    SimulatedBench bench;
    bench.set_voltage(5.0);
    for (double value : {-0.1, 24.1, std::numeric_limits<double>::quiet_NaN(),
                         std::numeric_limits<double>::infinity(),
                         -std::numeric_limits<double>::infinity()}) {
        EXPECT_THROW(bench.set_voltage(value), std::invalid_argument);
        EXPECT_DOUBLE_EQ(bench.read_voltage(), 5.0);
    }
}

TEST(SimulatedBenchTest, AcceptsTemperatureIncludingBoundaries) {
    SimulatedBench bench;
    for (double value : {-40.0, 0.0, 28.5, 95.0, 150.0}) {
        bench.set_temperature(value);
        EXPECT_DOUBLE_EQ(bench.read_temperature_c(), value);
    }
}

TEST(SimulatedBenchTest, RejectsInvalidTemperatureWithoutChangingState) {
    SimulatedBench bench;
    for (double value : {-40.1, 150.1, std::numeric_limits<double>::quiet_NaN(),
                         std::numeric_limits<double>::infinity(),
                         -std::numeric_limits<double>::infinity()}) {
        EXPECT_THROW(bench.set_temperature(value), std::invalid_argument);
        EXPECT_DOUBLE_EQ(bench.read_temperature_c(), 28.0);
    }
}

TEST(SimulatedBenchTest, CanDisconnectAndReconnect) {
    SimulatedBench bench;
    bench.set_connected(false);
    EXPECT_FALSE(bench.heartbeat_ok());
    bench.set_connected(true);
    EXPECT_TRUE(bench.heartbeat_ok());
}

TEST(SimulatedBenchTest, ConnectionChangesPreserveOtherState) {
    SimulatedBench bench(12.0, 65.0);
    bench.set_connected(false);
    EXPECT_DOUBLE_EQ(bench.read_voltage(), 12.0);
    EXPECT_DOUBLE_EQ(bench.read_temperature_c(), 65.0);
}

TEST(SimulatedBenchTest, SupportsValidatedInitialState) {
    const SimulatedBench bench(24.0, -40.0, false);
    EXPECT_DOUBLE_EQ(bench.read_voltage(), 24.0);
    EXPECT_DOUBLE_EQ(bench.read_temperature_c(), -40.0);
    EXPECT_FALSE(bench.heartbeat_ok());
}

TEST(SimulatedBenchTest, RejectsInvalidInitialState) {
    EXPECT_THROW((SimulatedBench{-1.0}), std::invalid_argument);
    EXPECT_THROW((SimulatedBench{0.0, 151.0}), std::invalid_argument);
    EXPECT_THROW((SimulatedBench{std::numeric_limits<double>::quiet_NaN()}),
                 std::invalid_argument);
    EXPECT_THROW((SimulatedBench{0.0, std::numeric_limits<double>::infinity()}),
                 std::invalid_argument);
}

TEST(SimulatedBenchTest, InstancesHaveIndependentState) {
    SimulatedBench changed;
    const SimulatedBench fresh;
    changed.set_voltage(12.0);
    changed.set_temperature(95.0);
    changed.set_connected(false);
    EXPECT_DOUBLE_EQ(fresh.read_voltage(), 0.0);
    EXPECT_DOUBLE_EQ(fresh.read_temperature_c(), 28.0);
    EXPECT_TRUE(fresh.heartbeat_ok());
}

}  // namespace
