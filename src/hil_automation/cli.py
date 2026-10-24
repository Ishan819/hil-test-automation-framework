"""Command-line entry point for running suites and saving JSON reports."""
import argparse
import sys
from pathlib import Path

from .config import Suite, load_suite
from .reporting import write_json_report
from .runner import run_suite


def main() -> int:
    parser = argparse.ArgumentParser(description="Run a simulated HIL test suite")
    parser.add_argument("config", help="Path to a YAML test suite")
    parser.add_argument("--report", default="reports/latest.json", help="JSON output path")
    selection = parser.add_mutually_exclusive_group()
    selection.add_argument(
        "--list-tests", action="store_true",
        help="List case names without executing tests or writing a report",
    )
    selection.add_argument("--case", metavar="NAME", help="Run only the named case")
    parser.add_argument("--verbose", action="store_true", help="Show step outcomes and timings")
    args = parser.parse_args()

    try:
        suite = load_suite(args.config)
        if args.list_tests:
            print(f"Suite: {suite.name}")
            for case in suite.tests:
                print(f"  {case.name}")
            return 0
        if args.case is not None:
            selected = [case for case in suite.tests if case.name == args.case]
            if not selected:
                available = ", ".join(case.name for case in suite.tests)
                raise ValueError(
                    f"Unknown test case: {args.case!r}. Available cases: {available}"
                )
            suite = Suite(suite.name, suite.bench, selected)
        result = run_suite(suite)
        output = Path(args.report)
        write_json_report(result, output)
    except (ValueError, OSError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2

    print(f"Suite: {result.suite}")
    for case in result.results:
        print(f"  [{case.status.upper():6}] {case.name} - {case.details}")
        if args.verbose:
            for step in case.steps:
                print(
                    f"    Step {step.index}: {step.action} [{step.status.upper()}] "
                    f"{step.duration_ms:.3f} ms - {step.details}"
                )
    print(f"Results: {result.passed} passed, {result.failed} failed")
    print(f"JSON report: {output}")
    return 1 if result.failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
