"""Opt-in wall-clock comparison of CPU-bound software-simulated suite execution."""
import argparse
import json
from pathlib import Path
from statistics import median, mean
from math import ceil
from time import perf_counter

from hil_automation.config import Suite, TestCase
from hil_automation.orchestration import run_plan
from hil_automation.plans import MAX_WORKERS, ExecutionPlan, PlanSuite


def bounded_integer(low, high):
    def parse(value):
        number = int(value)
        if not low <= number <= high:
            raise argparse.ArgumentTypeError(f"must be between {low} and {high}")
        return number
    return parse


def workload(suites, steps):
    return ExecutionPlan("benchmark", [
        PlanSuite(Path(f"simulated-{index}.yaml"), Suite(f"simulated-{index}", {"type": "simulated"}, [
            TestCase("voltage-cycle", [
                {"action": "set_voltage", "value": 5} if step % 2 == 0
                else {"action": "expect_voltage", "value": 5, "tolerance": 0}
                for step in range(steps)
            ]),
        ])) for index in range(suites)
    ])


def measure(suites, steps, workers):
    """Time real suite execution, with a new plan, benches and reports each time."""
    plan = workload(suites, steps)
    started = perf_counter()
    batch = run_plan(plan, workers=workers)
    elapsed = perf_counter() - started
    if batch.status != "passed" or len(batch.suites) != suites:
        raise RuntimeError("Benchmark workload did not complete successfully")
    return elapsed


def statistics(values, baseline):
    """p95 uses nearest rank ceil(.95*n), only for at least 20 samples."""
    middle = median(values)
    result = {
        "median_seconds": middle, "min_seconds": min(values),
        "max_seconds": max(values), "mean_seconds": mean(values),
        "speedup": baseline / middle if middle > 0 else None,
    }
    if len(values) >= 20:
        result["p95_seconds"] = sorted(values)[ceil(.95 * len(values)) - 1]
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--suites", type=bounded_integer(1, 128), default=8)
    parser.add_argument("--steps", type=bounded_integer(1, 100000), default=2000, help="Steps per suite")
    parser.add_argument("--repeats", type=bounded_integer(1, 100), default=3)
    parser.add_argument("--workers", type=int, choices=range(2, MAX_WORKERS + 1), default=4)
    parser.add_argument("--warmups", type=bounded_integer(0, 10), default=0)
    args = parser.parse_args()
    measurements = {1: [], args.workers: []}
    for repeat in range(-args.warmups, args.repeats):
        # Alternate order; warm-ups execute the same workload but are discarded.
        order = (1, args.workers) if repeat % 2 == 0 else (args.workers, 1)
        for workers in order:
            elapsed = measure(args.suites, args.steps, workers)
            if repeat >= 0:
                measurements[workers].append(elapsed)
    print(json.dumps({
        "workload": {"suites": args.suites, "steps_per_suite": args.steps, "repeats": args.repeats},
        "measurements": [{"workers": workers, "wall_seconds": values, **statistics(values, median(measurements[1]))}
                         for workers, values in measurements.items()],
        "note": "Execution only, including input snapshots; excludes plan construction and report writing. "
                "Threads do not guarantee faster execution, especially for this CPU-bound simulator.",
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
