#include "hil/protobuf_results.hpp"

#include <gtest/gtest.h>

#include <limits>
#include <stdexcept>

namespace {
namespace pb = hil::results::v1;

TEST(ProtobufResultTest, RoundTripsBenchResult) {
    const auto message = hil::bench_result(hil::SimulatedBench(5.0), "native-roundtrip");
    const auto decoded = hil::parse_result(hil::serialize_result(message));
    EXPECT_EQ(decoded.SerializeAsString(), message.SerializeAsString());
    EXPECT_EQ(decoded.schema_version(), 1);
    EXPECT_EQ(decoded.run_id(), "native-roundtrip");
    EXPECT_EQ(decoded.cases_size(), 3);
    EXPECT_EQ(decoded.summary().passed(), 3);
    EXPECT_GE(decoded.summary().duration_ms(), 0);
    EXPECT_EQ(decoded.cases(0).origin(), pb::NATIVE);
}

TEST(ProtobufResultTest, ActualBenchStateDeterminesFailures) {
    const auto message = hil::bench_result(hil::SimulatedBench(0, 95, false), "faults");
    EXPECT_EQ(message.summary().failed(), 3);
    EXPECT_EQ(message.summary().passed(), 0);
    EXPECT_EQ(message.cases(1).status(), pb::FAILED);
    EXPECT_NE(message.cases(1).details().find("95.000000"), std::string::npos);
    EXPECT_EQ(message.cases(2).failure_category(), "simulated_connection_failure");
}

TEST(ProtobufResultTest, RejectsIncompleteIdentityOrSummary) {
    EXPECT_THROW(hil::validate_result(pb::RunResult{}), std::invalid_argument);
    auto message = hil::bench_result(hil::SimulatedBench(5), "identity");
    message.set_run_id("");
    EXPECT_THROW(hil::validate_result(message), std::invalid_argument);
    message.set_run_id("identity");
    message.clear_summary();
    EXPECT_THROW(hil::validate_result(message), std::invalid_argument);
}

TEST(ProtobufResultTest, RejectsMalformedPayloadAndUnsupportedVersion) {
    EXPECT_THROW(hil::parse_result(std::string(1, static_cast<char>(0x80))), std::invalid_argument);
    EXPECT_THROW(hil::parse_result(""), std::invalid_argument);
    auto message = hil::bench_result(hil::SimulatedBench(5), "version");
    message.set_schema_version(2);
    EXPECT_THROW(hil::serialize_result(message), std::invalid_argument);
}

TEST(ProtobufResultTest, RejectsUnknownStatusAndInvalidDuration) {
    auto message = hil::bench_result(hil::SimulatedBench(5), "fields");
    message.mutable_cases(0)->set_status(static_cast<pb::Status>(99));
    EXPECT_THROW(hil::validate_result(message), std::invalid_argument);
    message.mutable_cases(0)->set_status(pb::PASSED);
    message.mutable_cases(0)->set_duration_ms(std::numeric_limits<double>::quiet_NaN());
    EXPECT_THROW(hil::validate_result(message), std::invalid_argument);
    message.mutable_cases(0)->set_duration_ms(-1);
    EXPECT_THROW(hil::validate_result(message), std::invalid_argument);
}

TEST(ProtobufResultTest, ChecksSummaryDuplicatesAndStepIndices) {
    auto message = hil::bench_result(hil::SimulatedBench(5), "counts");
    message.mutable_summary()->set_total(99);
    EXPECT_THROW(hil::validate_result(message), std::invalid_argument);
    message.mutable_summary()->set_total(3);
    auto* step = message.mutable_cases(0)->add_steps();
    step->set_index(2);
    step->set_action("read_voltage");
    step->set_status(pb::PASSED);
    EXPECT_THROW(hil::validate_result(message), std::invalid_argument);
    message.mutable_cases(0)->clear_steps();
    message.add_cases()->CopyFrom(message.cases(0));
    EXPECT_THROW(hil::validate_result(message), std::invalid_argument);
}

TEST(ProtobufResultTest, PreservesSkippedAndDisabledStatuses) {
    auto message = hil::bench_result(hil::SimulatedBench(5), "skips");
    message.mutable_cases(1)->set_status(pb::SKIPPED);
    message.mutable_cases(2)->set_status(pb::DISABLED);
    message.mutable_summary()->set_passed(1);
    message.mutable_summary()->set_skipped(2);
    const auto decoded = hil::parse_result(hil::serialize_result(message));
    EXPECT_EQ(decoded.cases(1).status(), pb::SKIPPED);
    EXPECT_EQ(decoded.cases(2).status(), pb::DISABLED);
    EXPECT_EQ(decoded.summary().skipped(), 2);
}

TEST(ProtobufResultTest, PreservesUnicodeAndChecksNativeExitCode) {
    auto message = hil::bench_result(hil::SimulatedBench(5), u8"run-π");
    EXPECT_EQ(hil::parse_result(hil::serialize_result(message)).run_id(), u8"run-π");
    message.set_native_exit_code(7);
    EXPECT_THROW(hil::validate_result(message), std::invalid_argument);
}
}  // namespace
