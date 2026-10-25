cmake_minimum_required(VERSION 3.20)
project(HilBenchNative VERSION 0.1.0 LANGUAGES CXX)

add_library(hil_simulated_bench src/simulated_bench.cpp)
target_include_directories(hil_simulated_bench PUBLIC "${CMAKE_CURRENT_SOURCE_DIR}/include")
target_compile_features(hil_simulated_bench PUBLIC cxx_std_17)
set_target_properties(hil_simulated_bench PROPERTIES CXX_EXTENSIONS OFF)
