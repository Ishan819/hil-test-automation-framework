#include "hil/protobuf_results.hpp"

#include <algorithm>
#include <chrono>
#include <cmath>
#include <cctype>
#include <set>
#include <stdexcept>
#include <tuple>

namespace hil {
namespace {
namespace pb = results::v1;
using Clock = std::chrono::steady_clock;
constexpr std::size_t max_payload = 16 * 1024 * 1024;

bool nonblank(const std::string& value) {
    return std::any_of(value.begin(), value.end(), [](unsigned char ch) { return !std::isspace(ch); });
}

void require(bool condition, const char* message) {
    if (!condition) {
        throw std::invalid_argument(message);
    }
}

void duration(double value) {
    require(std::isfinite(value) && value >= 0, "Durations must be finite and non-negative");
}

void add_case(pb::RunResult& result, const std::string& name, bool passed,
              const std::string& details, Clock::time_point started,
              const std::string& category = "native_test_failure") {
    auto* item = result.add_cases();
    item->set_suite(result.suite());
    item->set_name(name);
    item->set_origin(pb::NATIVE);
    item->set_status(passed ? pb::PASSED : pb::FAILED);
    item->set_details(details);
    if (!passed) {
        item->set_failure_category(category);
    }
    item->set_duration_ms(std::chrono::duration<double, std::milli>(Clock::now() - started).count());
    auto* summary = result.mutable_summary();
    summary->set_total(summary->total() + 1);
    if (passed) {
        summary->set_passed(summary->passed() + 1);
    } else {
        summary->set_failed(summary->failed() + 1);
    }
}
}  // namespace

void validate_result(const pb::RunResult& result) {
    require(result.schema_version() == 1, "Unsupported Protobuf schema version");
    require(nonblank(result.run_id()) && nonblank(result.suite()), "Run ID and suite name are required");
    require(result.has_summary(), "Run summary is required");
    duration(result.summary().duration_ms());
    std::set<std::tuple<int, std::string, std::string>> seen;
    unsigned passed = 0, failed = 0, skipped = 0;
    bool native_failed = false;
    for (const auto& item : result.cases()) {
        require(nonblank(item.name()) && nonblank(item.suite()), "Case and suite names are required");
        require(item.origin() == pb::PYTHON || item.origin() == pb::NATIVE, "Unsupported case origin");
        require(item.status() >= pb::PASSED && item.status() <= pb::DISABLED, "Unsupported case status");
        require(item.status() != pb::DISABLED || item.origin() == pb::NATIVE, "Only native cases can be disabled");
        require(seen.emplace(item.origin(), item.suite(), item.name()).second, "Duplicate case identity");
        duration(item.duration_ms());
        require(item.status() != pb::FAILED || nonblank(item.details()), "Failed cases require diagnostic details");
        unsigned index = 0;
        for (const auto& step : item.steps()) {
            require(step.index() == ++index && nonblank(step.action()), "Invalid step index or action");
            require(step.status() >= pb::PASSED && step.status() <= pb::SKIPPED, "Unsupported step status");
            require(step.status() != pb::FAILED || nonblank(step.details()), "Failed steps require diagnostic details");
            duration(step.duration_ms());
        }
        passed += item.status() == pb::PASSED;
        failed += item.status() == pb::FAILED;
        skipped += item.status() == pb::SKIPPED || item.status() == pb::DISABLED;
        native_failed |= item.origin() == pb::NATIVE && item.status() == pb::FAILED;
    }
    const auto& summary = result.summary();
    require(summary.total() == static_cast<unsigned>(result.cases_size())
            && summary.passed() == passed && summary.failed() == failed && summary.skipped() == skipped,
            "Run summary does not match case outcomes");
    if (result.has_native_exit_code()) {
        require(result.native_exit_code() == 0 ? !native_failed : native_failed,
                "Native exit code does not match native outcomes");
    }
}

std::string serialize_result(const pb::RunResult& result) {
    validate_result(result);
    std::string payload;
    require(result.SerializeToString(&payload), "Cannot serialize Protobuf result");
    require(payload.size() <= max_payload, "Protobuf payload exceeds 16 MiB");
    return payload;
}

pb::RunResult parse_result(std::string_view payload) {
    require(payload.size() <= max_payload, "Protobuf payload exceeds 16 MiB");
    pb::RunResult result;
    require(result.ParseFromArray(payload.data(), static_cast<int>(payload.size())),
            "Malformed Protobuf result payload");
    validate_result(result);
    return result;
}

pb::RunResult bench_result(const SimulatedBench& bench, const std::string& run_id) {
    const auto started = Clock::now();
    pb::RunResult result;
    result.set_schema_version(1);
    result.set_run_id(run_id);
    result.set_suite("cpp-simulated-bench");

    auto check_started = Clock::now();
    const auto voltage = bench.read_voltage();
    add_case(result, "voltage_is_five_volts", std::abs(voltage - 5.0) <= 0.1,
             "Measured voltage: " + std::to_string(voltage) + " V; expected 5 +/- 0.1 V", check_started);
    check_started = Clock::now();
    const auto temperature = bench.read_temperature_c();
    add_case(result, "temperature_below_75", temperature < 75.0,
             "Measured temperature: " + std::to_string(temperature) + " C; expected below 75 C", check_started);
    check_started = Clock::now();
    const bool connected = bench.heartbeat_ok();
    add_case(result, "device_heartbeat", connected,
             connected ? "Simulated device connected" : "Simulated device disconnected",
             check_started, "simulated_connection_failure");
    result.mutable_summary()->set_duration_ms(
        std::chrono::duration<double, std::milli>(Clock::now() - started).count());
    validate_result(result);
    return result;
}

}  // namespace hil
