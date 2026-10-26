# HIL Bench

A personal project I'm working on to explore hardware testing and automation. The idea is to build a tool that can run tests, check simulated hardware behavior, and help identify failures without having to test everything manually. I'm starting with Python and a basic simulator, and I'll keep adding features as I work on it.
## C++ simulation tests

Requires CMake 3.20+, a C++17 compiler, and Git on macOS or Linux.
The first configure downloads GoogleTest v1.17.0 at a pinned revision.

```bash
cmake -S cpp -B build/cpp
cmake --build build/cpp
ctest --test-dir build/cpp --output-on-failure
hil-run --native-tests build/cpp/hil_bench_tests --native-timeout 30
```

Install the Python package first with `python -m pip install -e ".[dev]"`.
Native tests run in a separate process with their own simulator; they do not
share Python bench state. Use `--native-results` for individual GoogleTest outcomes,
or `--report reports/native.json` to capture them in a HIL report. Add
`--report-format junit` for JUnit XML. Report options automatically enable XML capture;
without them, raw native execution remains unchanged. Native mode supports
`--verbose` and `--quiet`. CLI exit codes are 0 for success, 1 for test failure,
and 2 for launch, timeout, or argument errors. YAML commands work as before.


To include the optional mixed-outcome reporting fixture, configure with
`cmake -S cpp -B build/cpp -DHIL_BUILD_REPORTING_FIXTURE=ON` and rebuild.
Run `python -m pytest -q -m native_integration` for real-binary reporting tests.
These tests skip when their binaries are absent; CI builds and requires both.
The intentionally failing fixture is separate from the passing CTest suite.
