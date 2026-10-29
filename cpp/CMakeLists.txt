cmake_minimum_required(VERSION 3.20)
project(HilBenchNative VERSION 0.1.0 LANGUAGES CXX)

add_library(hil_simulated_bench src/simulated_bench.cpp)
target_include_directories(hil_simulated_bench PUBLIC "${CMAKE_CURRENT_SOURCE_DIR}/include")
target_compile_features(hil_simulated_bench PUBLIC cxx_std_17)
set_target_properties(hil_simulated_bench PROPERTIES CXX_EXTENSIONS OFF)

include(CTest)
if(BUILD_TESTING)
    include(FetchContent)
    FetchContent_Declare(
        googletest
        GIT_REPOSITORY https://github.com/google/googletest.git
        # GoogleTest v1.17.0, pinned to an immutable revision.
        GIT_TAG 52eb8108c5bdec04579160ae17225d66034bd723
    )
    set(INSTALL_GTEST OFF CACHE BOOL "" FORCE)
    set(BUILD_GMOCK OFF CACHE BOOL "" FORCE)
    FetchContent_MakeAvailable(googletest)

    add_executable(hil_bench_tests tests/test_simulated_bench.cpp)
    target_link_libraries(hil_bench_tests PRIVATE hil_simulated_bench GTest::gtest_main)
    set_target_properties(hil_bench_tests PROPERTIES CXX_EXTENSIONS OFF)
    include(GoogleTest)
    gtest_discover_tests(hil_bench_tests)
endif()

# Optional mixed-outcome binary for Python end-to-end reporting tests.
option(HIL_BUILD_REPORTING_FIXTURE "Build intentionally failing reporting fixture" OFF)
if(BUILD_TESTING AND HIL_BUILD_REPORTING_FIXTURE)
    add_executable(hil_reporting_fixture tests/reporting_fixture.cpp)
    target_compile_features(hil_reporting_fixture PRIVATE cxx_std_17)
    target_link_libraries(hil_reporting_fixture PRIVATE GTest::gtest_main)
    set_target_properties(hil_reporting_fixture PROPERTIES CXX_EXTENSIONS OFF)
endif()

# Build protoc and its C++ runtime together; never use an unrelated system library.
include(FetchContent)
set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(protobuf_BUILD_TESTS OFF CACHE BOOL "" FORCE)
set(protobuf_INSTALL OFF CACHE BOOL "" FORCE)
set(protobuf_BUILD_LIBUPB ON CACHE BOOL "" FORCE)
set(protobuf_WITH_ZLIB OFF CACHE BOOL "" FORCE)
set(protobuf_FORCE_FETCH_DEPENDENCIES ON CACHE BOOL "" FORCE)
set(ABSL_PROPAGATE_CXX_STD ON CACHE BOOL "" FORCE)
# The Abseil revision used by Protobuf v33.6 (20250512.1).
FetchContent_Declare(absl
    GIT_REPOSITORY https://github.com/abseil/abseil-cpp.git
    GIT_TAG 76bb24329e8bf5f39704eb10d21b9a80befa7c81
)
FetchContent_Declare(
    protobuf
    GIT_REPOSITORY https://github.com/protocolbuffers/protobuf.git
    # Protobuf v33.6; compiler and runtime use this exact revision.
    GIT_TAG 6e1998413a5bca7c058b85999667893f167434bc
    GIT_SUBMODULES ""
)
FetchContent_MakeAvailable(protobuf)

set(HIL_SCHEMA "${CMAKE_CURRENT_SOURCE_DIR}/../proto/hil_results.proto")
set(HIL_PROTO_OUTPUT "${CMAKE_CURRENT_BINARY_DIR}/generated")
file(MAKE_DIRECTORY "${HIL_PROTO_OUTPUT}")
add_custom_command(
    OUTPUT "${HIL_PROTO_OUTPUT}/hil_results.pb.cc" "${HIL_PROTO_OUTPUT}/hil_results.pb.h"
    COMMAND protobuf::protoc
    ARGS "--proto_path=${CMAKE_CURRENT_SOURCE_DIR}/../proto"
         "--cpp_out=${HIL_PROTO_OUTPUT}" "${HIL_SCHEMA}"
    DEPENDS protobuf::protoc "${HIL_SCHEMA}"
    VERBATIM
)
add_library(hil_result_proto "${HIL_PROTO_OUTPUT}/hil_results.pb.cc")
target_include_directories(hil_result_proto PUBLIC "${HIL_PROTO_OUTPUT}")
target_link_libraries(hil_result_proto PUBLIC protobuf::libprotobuf)
target_compile_features(hil_result_proto PUBLIC cxx_std_17)

find_package(Python3 3.10 REQUIRED COMPONENTS Interpreter)
add_custom_target(check_python_proto
    COMMAND "${Python3_EXECUTABLE}" "${CMAKE_CURRENT_SOURCE_DIR}/../tools/generate_proto.py"
            --protoc "$<TARGET_FILE:protobuf::protoc>" --check
    DEPENDS protobuf::protoc
    VERBATIM
)

add_library(hil_protobuf_results src/protobuf_results.cpp)
target_include_directories(hil_protobuf_results PUBLIC "${CMAKE_CURRENT_SOURCE_DIR}/include")
target_link_libraries(hil_protobuf_results PUBLIC hil_result_proto hil_simulated_bench)
target_compile_features(hil_protobuf_results PUBLIC cxx_std_17)

if(BUILD_TESTING)
    add_executable(hil_proto_tests tests/test_protobuf_results.cpp)
    target_link_libraries(hil_proto_tests PRIVATE hil_protobuf_results GTest::gtest_main)
    gtest_discover_tests(hil_proto_tests)
endif()

add_executable(hil_proto_exchange src/proto_exchange.cpp)
target_link_libraries(hil_proto_exchange PRIVATE hil_protobuf_results)
