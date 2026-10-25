"""Run YAML suites with reports or execute a separate native test binary."""
import argparse
import sys
from pathlib import Path

from .config import Suite, load_suite
from .native import NativeExecutionError, run_native_tests
from .reporting import write_json_report, write_junit_report
from .runner import run_suite


def _run_native(args: argparse.Namespace) -> int:
    try:
        result = run_native_tests(
            args.native_tests,
            timeout=args.native_timeout if args.native_timeout is not None else 30.0,
        )
    except (NativeExecutionError, ValueError, OSError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2
    if args.verbose:
        print(f"Native executable: {result.executable}")
        print(f"Native duration: {result.duration_ms:.3f} ms")
    if not args.quiet and result.stdout:
        print(result.stdout, end="" if result.stdout.endswith("\n") else "\n")
    if result.stderr:
        print(result.stderr, end="", file=sys.stderr)
    status = "passed" if result.exit_code == 0 else "failed"
    print(f"Native tests: {status} (exit code {result.exit_code})")
    return 0 if result.exit_code == 0 else 1


def main() -> int:
    parser = argparse.ArgumentParser(description="Run a simulated HIL test suite")
    parser.add_argument("config", nargs="?", help="Path to a YAML test suite")
    parser.add_argument(
        "--native-tests", metavar="BINARY",
        help="Run a compiled test binary in a separate process instead of a YAML suite",
    )
    parser.add_argument(
        "--native-timeout", type=float, metavar="SECONDS",
        help="Native process timeout in seconds (default: 30; requires --native-tests)",
    )
    parser.add_argument(
        "--report", help="Output path (default: reports/latest.json or reports/latest.xml)",
    )
    parser.add_argument(
        "--report-format", choices=("json", "junit"),
        help="Report format: json (default) or junit (JUnit XML)",
    )
    selection = parser.add_mutually_exclusive_group()
    selection.add_argument(
        "--list-tests", action="store_true",
        help="List case names without executing tests or writing a report",
    )
    selection.add_argument("--case", metavar="NAME", help="Run only the named case")
    output_mode = parser.add_mutually_exclusive_group()
    output_mode.add_argument("--verbose", action="store_true", help="Show step outcomes and timings")
    output_mode.add_argument("--quiet", action="store_true", help="Print only the results summary")
    parser.add_argument(
        "--fail-fast", action="store_true", help="Stop execution after the first failed case",
    )
    args = parser.parse_args()
    if args.native_tests is not None:
        if args.config is not None:
            parser.error("provide either a YAML config or --native-tests, not both")
        if (
            args.list_tests or args.case is not None or args.fail_fast
            or args.report is not None or args.report_format is not None
        ):
            parser.error("--native-tests cannot be combined with YAML selection or report options")
        return _run_native(args)
    if args.config is None:
        parser.error("provide a YAML config or --native-tests BINARY")
    if args.native_timeout is not None:
        parser.error("--native-timeout requires --native-tests")
    args.report_format = args.report_format or "json"

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
        result = run_suite(suite, fail_fast=args.fail_fast)
        suffix = "json" if args.report_format == "json" else "xml"
        output = Path(args.report) if args.report is not None else Path(f"reports/latest.{suffix}")
        if args.report_format == "json":
            write_json_report(result, output)
        else:
            write_junit_report(result, output)
    except (ValueError, OSError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2

    if not args.quiet:
        print(f"Suite: {result.suite}")
        for case in result.results:
            print(f"  [{case.status.upper():6}] {case.name} - {case.details}")
            if args.verbose:
                for step in case.steps:
                    print(
                        f"    Step {step.index}: {step.action} [{step.status.upper()}] "
                        f"{step.duration_ms:.3f} ms - {step.details}"
                    )
    summary = f"Results: {result.passed} passed, {result.failed} failed"
    if result.skipped:
        summary += f", {result.skipped} skipped"
    print(summary)
    if not args.quiet:
        label = "JSON" if args.report_format == "json" else "JUnit XML"
        print(f"{label} report: {output}")
    return 1 if result.failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
