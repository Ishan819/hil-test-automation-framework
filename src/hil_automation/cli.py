"""Command-line entry point for running suites and saving JSON reports."""
import argparse
import json
import sys
from pathlib import Path

from .config import load_suite
from .runner import run_suite


def main() -> int:
    parser = argparse.ArgumentParser(description="Run a simulated HIL test suite")
    parser.add_argument("config", help="Path to a YAML test suite")
    parser.add_argument("--report", default="reports/latest.json", help="JSON output path")
    parser.add_argument(
        "--list-tests", action="store_true",
        help="List case names without executing tests or writing a report",
    )
    args = parser.parse_args()

    try:
        suite = load_suite(args.config)
        if args.list_tests:
            print(f"Suite: {suite.name}")
            for case in suite.tests:
                print(f"  {case.name}")
            return 0
        result = run_suite(suite)
        output = Path(args.report)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(result.to_dict(), indent=2) + "\n", encoding="utf-8")
    except (ValueError, OSError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2

    print(f"Suite: {result.suite}")
    for case in result.results:
        print(f"  [{case.status.upper():6}] {case.name} - {case.details}")
    print(f"Results: {result.passed} passed, {result.failed} failed")
    print(f"JSON report: {output}")
    return 1 if result.failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
