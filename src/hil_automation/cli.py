"""Run YAML suites with reports or execute a separate native test binary."""
import argparse
import sys
from pathlib import Path

from .config import Suite, load_suite
from .native import NativeExecutionError, run_native_tests
from .orchestration import run_plan, write_batch_report
from .plans import load_plan
from .reporting import native_report, write_json_report, write_junit_report, write_protobuf_report
from .runner import run_suite


def _run_native(args: argparse.Namespace) -> int:
    report_requested = args.report is not None or args.report_format is not None
    structured = args.native_results or report_requested or args.native_filter is not None
    try:
        result = run_native_tests(
            args.native_tests,
            timeout=args.native_timeout if args.native_timeout is not None else 30.0,
            capture_xml=structured, native_filter=args.native_filter,
        )
    except NativeExecutionError as exc:
        if args.verbose and exc.stdout:
            print(exc.stdout, end="" if exc.stdout.endswith("\n") else "\n")
        if exc.stderr:
            print(exc.stderr, end="", file=sys.stderr)
        print(f"Error: {exc}", file=sys.stderr)
        return 2
    except (ValueError, OSError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2
    if args.verbose:
        print(f"Native executable: {result.executable}")
        print(f"Native duration: {result.duration_ms:.3f} ms")
    if not args.quiet and result.stdout and (not structured or args.verbose):
        print(result.stdout, end="" if result.stdout.endswith("\n") else "\n")
    if result.stderr:
        print(result.stderr, end="", file=sys.stderr)
    if result.result_error is not None:
        print(f"Error: {result.result_error}", file=sys.stderr)
        return 2
    if report_requested:
        report_format = args.report_format or "json"
        suffix = {"json": "json", "junit": "xml", "protobuf": "pb"}[report_format]
        output = Path(args.report) if args.report is not None else Path(f"reports/latest.{suffix}")
        try:
            report = native_report(result)
            if report_format == "json":
                write_json_report(report, output)
            elif report_format == "junit":
                write_junit_report(report, output)
            else:
                write_protobuf_report(report, output)
        except (ValueError, OSError) as exc:
            print(f"Error: {exc}", file=sys.stderr)
            return 2
        if not args.quiet:
            label = {"json": "JSON", "junit": "JUnit XML", "protobuf": "Protobuf"}[report_format]
            print(f"{label} report: {output}")
    if structured:
        if not args.quiet:
            for case in result.cases:
                timing = f" ({case.duration_ms:.3f} ms)" if args.verbose else ""
                print(f"  [{case.status.upper():8}] {case.suite}.{case.name}{timing} - {case.details}")
        passed = sum(case.status == "passed" for case in result.cases)
        failed = sum(case.status == "failed" for case in result.cases)
        skipped = sum(case.status in ("skipped", "disabled") for case in result.cases)
        print(f"Native results: {passed} passed, {failed} failed, {skipped} skipped")
    else:
        status = "passed" if result.successful else "failed"
        print(f"Native tests: {status} (exit code {result.exit_code})")
    return 0 if result.successful else 1


def _run_plan(args: argparse.Namespace) -> int:
    try:
        batch = run_plan(load_plan(args.plan), fail_fast=args.fail_fast)
        manifest = write_batch_report(
            batch, args.report_dir or "reports/plans", args.report_format or "json",
        )
    except (ValueError, OSError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2
    if not args.quiet:
        print(f"Plan: {batch.plan}")
        for suite in batch.suites:
            print(f"  [{suite.status.upper():7}] {suite.name} - {suite.duration_ms:.3f} ms")
            if args.verbose and suite.report:
                for case in suite.report.results:
                    print(f"    [{case.status.upper()}] {case.name} - {case.details}")
        print(f"Batch report: {manifest}")
    statistics = batch.to_dict()["statistics"]
    print(
        f"Batch results: {statistics['passed_suites']} passed, "
        f"{statistics['failed_suites']} failed, {statistics['skipped_suites']} skipped"
    )
    return 1 if batch.status == "failed" else 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Run a simulated HIL test suite")
    parser.add_argument("config", nargs="?", help="Path to a YAML test suite")
    parser.add_argument("--plan", metavar="YAML", help="Run an ordered YAML execution plan")
    parser.add_argument(
        "--report-dir", metavar="DIRECTORY",
        help="Batch output root (requires --plan; default: reports/plans). Manifest is JSON.",
    )
    parser.add_argument(
        "--native-tests", metavar="BINARY",
        help="Run a compiled test binary in a separate process instead of a YAML suite",
    )
    parser.add_argument(
        "--native-results", action="store_true",
        help="Capture and display individual GoogleTest XML results (requires --native-tests)",
    )
    parser.add_argument(
        "--native-filter", metavar="PATTERN",
        help="GoogleTest filter (requires --native-tests; no matches returns exit code 2)",
    )
    parser.add_argument(
        "--native-timeout", type=float, metavar="SECONDS",
        help="Native process timeout in seconds (default: 30; requires --native-tests)",
    )
    parser.add_argument(
        "--report", help="Output path (default: reports/latest.json, .xml, or .pb for the selected format)",
    )
    parser.add_argument(
        "--report-format", choices=("json", "junit", "protobuf"),
        help="Report format: json (default), junit (JUnit XML), or protobuf (binary)",
    )
    selection = parser.add_mutually_exclusive_group()
    selection.add_argument(
        "--list-tests", action="store_true",
        help="List case names without executing tests or writing a report",
    )
    selection.add_argument("--case", metavar="NAME", help="Run only the named case")
    selection.add_argument("--tag", metavar="TAG", help="Run YAML cases with the exact tag")
    output_mode = parser.add_mutually_exclusive_group()
    output_mode.add_argument("--verbose", action="store_true", help="Show step outcomes and timings")
    output_mode.add_argument("--quiet", action="store_true", help="Print only the results summary")
    parser.add_argument(
        "--fail-fast", action="store_true", help="Stop execution after the first failed case",
    )
    args = parser.parse_args()
    if args.plan is not None:
        if (
            args.config is not None or args.native_tests is not None or args.native_results
            or args.native_filter is not None or args.native_timeout is not None
            or args.case is not None or args.tag is not None or args.list_tests
            or args.report is not None
        ):
            parser.error("--plan cannot be combined with single-suite, native, selection, or --report options")
        return _run_plan(args)
    if args.report_dir is not None:
        parser.error("--report-dir requires --plan")
    if args.native_tests is not None:
        if args.config is not None:
            parser.error("provide either a YAML config or --native-tests, not both")
        if (
            args.list_tests or args.case is not None or args.tag is not None or args.fail_fast
        ):
            parser.error("--native-tests cannot be combined with YAML selection options")
        return _run_native(args)
    if args.native_filter is not None:
        parser.error("--native-filter requires --native-tests")
    if args.config is None:
        parser.error("provide a YAML config or --native-tests BINARY")
    if args.native_timeout is not None:
        parser.error("--native-timeout requires --native-tests")
    if args.native_results:
        parser.error("--native-results requires --native-tests")
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
        elif args.tag is not None:
            if not args.tag.strip() or args.tag != args.tag.strip():
                raise ValueError("Tag must be a non-empty name without surrounding whitespace")
            selected = [case for case in suite.tests if args.tag in case.tags]
            if not selected:
                available = ", ".join(sorted({tag for case in suite.tests for tag in case.tags})) or "(none)"
                raise ValueError(f"Unknown tag: {args.tag!r}. Available tags: {available}")
            suite = Suite(suite.name, suite.bench, selected)
        result = run_suite(suite, fail_fast=args.fail_fast)
        suffix = {"json": "json", "junit": "xml", "protobuf": "pb"}[args.report_format]
        output = Path(args.report) if args.report is not None else Path(f"reports/latest.{suffix}")
        if args.report_format == "json":
            write_json_report(result, output)
        elif args.report_format == "junit":
            write_junit_report(result, output)
        else:
            write_protobuf_report(result, output)
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
        label = {"json": "JSON", "junit": "JUnit XML", "protobuf": "Protobuf"}[args.report_format]
        print(f"{label} report: {output}")
    return 1 if result.failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
