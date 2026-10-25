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
