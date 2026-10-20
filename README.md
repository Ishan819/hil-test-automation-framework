# HIL Test Automation Framework

A small but working, configuration-driven test runner that executes automated checks against a **simulated Hardware-in-the-Loop (HIL) bench**. Built as a foundation for a larger Python + C++ HIL framework.

> **Current scope (v0.1):** Software simulation only. No physical hardware, real-time scheduling, C++/GoogleTest integration, or Protocol Buffers transport has been implemented yet.

## What it does today

- Loads a suite of test scenarios from YAML.
- Validates known test actions and their required inputs.
- Creates an isolated simulated bench for each test case.
- Checks voltage, temperature, and heartbeat assertions.
- Prints pass/fail results and writes a JSON failure-triage report.
- Returns a nonzero exit code for failing suites (useful for CI).
- Runs a Python/pytest suite automatically via GitHub Actions.

## Quick start (macOS/Linux)

Requires Python 3.10+.

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
python -m pytest -q
hil-run scenarios/smoke.yaml
```

The sample suite should produce:

```text
Suite: bench-smoke-tests
  [PASSED] power_rail_reaches_five_volts - All steps passed
  [PASSED] device_is_not_overheating - All steps passed
  [PASSED] device_responds_to_heartbeat - All steps passed
Results: 3 passed, 0 failed
JSON report: reports/latest.json
```

Inspect the JSON output with `cat reports/latest.json`.

## Demonstrate a failure

```bash
hil-run scenarios/failure_demo.yaml --report reports/failures.json
```

This command is **supposed** to return exit code 1. It reports both the over-temperature and disconnected heartbeat cases. This is how an automation system distinguishes a passing suite from a failed one.

## Project layout

```text
scenarios/                 YAML test definitions (no Python edits needed)
src/hil_automation/
  bench.py                 Bench interface + mock hardware implementation
  config.py                Safe YAML parsing and validation
  runner.py                Executes steps and produces case results
  cli.py                   Terminal command and JSON report writer
tests/                     pytest unit / CLI integration tests
.github/workflows/         GitHub Actions tests on push and PR
```

## How the test pipeline works

```text
YAML scenario
    │
    v
Config validation -> test case -> simulated bench -> action/assertion
                                          │
                                          v
                                    pass/fail result
                                          │
                                          v
                                  console + JSON report
```

An example test step:

```yaml
- action: expect_voltage
  value: 5.0
  tolerance: 0.1
```

The runner reads this instruction, calls the bench's voltage measurement method and marks the test as failed if the measurement falls outside the ±0.1 V tolerance.

## Roadmap (not yet implemented)

1. Support execution of C++ GoogleTest binaries as subprocesses.
2. Define and use Protocol Buffers to exchange results and metadata.
3. Add configurable retry/timeout policies, job scheduling, and full regression suites.
4. Add a hardware adapter (serial / TCP / real HIL bench) and release qualification reporting.

## GitHub

To publish the project as a new repository, create an empty repo named `hil-test-automation-framework` on GitHub **without** generating a README, then run:

```bash
git init
git add .
git commit -m "Initial simulated HIL test runner with YAML scenarios and pytest"
git branch -M main
git remote add origin https://github.com/YOUR_USERNAME/hil-test-automation-framework.git
git push -u origin main
```

Replace `YOUR_USERNAME` with your GitHub username. Git may ask you to authenticate. Do not commit the local `.venv` directory or generated `reports/` directory (both are ignored).
