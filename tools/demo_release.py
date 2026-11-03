"""Reproduce passing and rejected software-only release qualification evidence."""
import argparse
import json
from pathlib import Path

from hil_automation.orchestration import run_plan, write_batch_report
from hil_automation.plans import MAX_WORKERS, load_plan
from hil_automation.qualification import evaluate_qualification
from hil_automation.qualification_policy import load_policy
from hil_automation.reporting import write_qualification_report

ROOT = Path(__file__).resolve().parents[1]


def demonstrate(output, workers):
    policy = load_policy(ROOT / "policies/strict.yaml")
    demonstrations = []
    for name, expected in (("recovery", True), ("faults", False)):
        plan = load_plan(ROOT / f"plans/{name}.yaml")
        batch = run_plan(plan, workers=workers)
        manifest = write_batch_report(batch, output, "protobuf")
        result = evaluate_qualification(batch, policy, expected=plan)
        qualification_path = manifest.parent / "qualification.json"
        write_qualification_report(result, qualification_path)
        evidence = result.to_dict()
        if not result.complete or result.qualified != expected or (batch.status == "passed") != expected:
            raise ValueError(f"Unexpected {name} demonstration outcome; inspect exported evidence")
        demonstrations.append({
            "example": name, "execution_status": batch.status,
            "manifest": str(manifest), "qualification_report": str(qualification_path),
            "decision": evidence["decision"], "observed": evidence["observed"],
            "criteria": evidence["criteria"], "failure_reasons": evidence["failure_reasons"],
            "execution_references": evidence["execution_references"],
        })
    return demonstrations


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=Path("reports/demo"))
    parser.add_argument("--workers", type=int, choices=range(1, MAX_WORKERS + 1), default=2)
    args = parser.parse_args()
    try:
        results = demonstrate(args.output_dir, args.workers)
    except (ValueError, OSError) as exc:
        parser.exit(2, f"Demo failed: {exc}\n")
    print(json.dumps({"scope": "simulated_software_tests", "demonstrations": results}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
