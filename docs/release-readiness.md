# Release candidate audit — 2026-11-13

This records local verification of the simulated HIL Bench project after the
Day 17 audit. It is a candidate for code review, not a published release or
qualification of physical hardware. Package version remains `0.1.0`.

The starting branch was clean `main` at `44408f2`. A read-only remote check
confirmed that Day 16 was pushed before this work began.

## Correctness changes

- Scenario and plan loaders reject duplicate explicit YAML fields that could
  silently replace test inventories or assertion parameters. Existing aliases
  and explicit overrides of merge defaults remain valid.
- Qualification rejects retryable failures whose histories stop before the
  configured attempt limit, including under permissive acceptance policies.
  Early success and nonretryable failures retain their existing behavior.
- The release demo validates complete reports through the existing CI evidence
  validator, rejects symlinked scenario directories, and bounds each CLI
  subprocess with a 120-second watchdog.
- Clean installation verification now checks dependency consistency, CLI version
  metadata, and Python-only diagnostics without optional native tools on PATH.
  No dependency versions were changed.

The regression cases for overwritten YAML inventories, truncated retry evidence,
missing demo reports, and redirected demo output failed before their respective
fixes and passed afterward.

## Verified locally

Environment: Python **3.12.15**, macOS/arm64, PyYAML **6.0.3**, Protobuf runtime
**6.33.6**. Native dependencies were available in the existing CMake build cache.

| Check | Result |
| --- | --- |
| `python -m pytest -q --cov --cov-report=term-missing --cov-report=xml:reports/day17-coverage.xml` | 798 passed; reported combined statement/branch coverage 97%, excluding generated bindings |
| `python tools/verify_install.py` | Fresh wheel build/install, dependency check, version, Python-only doctor, JSON/Protobuf output, and installed demo passed |
| CMake configure/build with `HIL_BUILD_REPORTING_FIXTURE=ON` | Passed |
| `ctest --test-dir build/cpp --output-on-failure --no-tests=error` | 19 passed |
| `cmake --build build/cpp --target check_python_proto` | Tracked bindings match pinned protoc 33.6 |
| pytest native/Protobuf integration selection with all three binary paths explicitly configured | 44 passed; this is a subset of the full suite |
| Demo with workers 1 and 2; documented CLI execution examples | Expected exit codes and evidence verified |
| CI evidence generation, validation, and summary | Passed; recovery: 6 passed/0 failed/qualified; faults: 6 passed/2 failed/not qualified |
| Documented optional benchmark, 20 repeats with 2 warm-ups | Completed; measurements retained locally without a speed claim or CI threshold |
| `git diff --check origin/main..HEAD` | Passed |

Generated evidence, coverage, installation logs, and benchmark measurements remain
under ignored `reports/`; temporary installation environments are cleaned up.
Use the README commands to reproduce the checks rather than relying on old reports.

## Remaining verification and limits

Hosted GitHub Actions, its Linux runners, and the Python 3.10/3.11 matrix were not
executed locally. A fresh download of every native dependency was not tested;
the existing pinned dependency cache was used. The wheel verification did install
its declared runtime dependencies in a new temporary environment.

Physical hardware adapters, hard timeouts for in-process Python steps, real-time
guarantees, and safety certification are outside the implemented scope. Parallel
fail-fast remains unsupported. No release tag or remote publication is part of
this local audit.
