#pragma once

#include "hil/simulated_bench.hpp"
#include "hil_results.pb.h"

#include <string>
#include <string_view>

namespace hil {

void validate_result(const results::v1::RunResult& result);
std::string serialize_result(const results::v1::RunResult& result);
results::v1::RunResult parse_result(std::string_view payload);
results::v1::RunResult bench_result(const SimulatedBench& bench, const std::string& run_id);

}  // namespace hil
