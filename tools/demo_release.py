"""Reproduce passing and rejected software-only release qualification evidence."""
import argparse
import json
from pathlib import Path

import subprocess
import sys
from uuid import uuid4
from xml.etree.ElementTree import ParseError

from validate_ci_evidence import validate_examples

from hil_automation.plans import MAX_WORKERS

ROOT = Path(__file__).resolve().parents[1]


def demonstrate(output, workers):
    output = Path(output).resolve()
    if (output / "scenarios").is_symlink():
        raise ValueError("Scenario output must not be a symbolic link")
    scenario_dir = output / "scenarios" / str(uuid4())
    scenario_dir.mkdir(parents=True)

    def execute(arguments, expected):
        try:
            process = subprocess.run([sys.executable, "-m", "hil_automation.cli", *map(str, arguments)],
                                     cwd=ROOT, capture_output=True, text=True, timeout=120)
        except subprocess.TimeoutExpired as exc:
            raise ValueError("CLI timed out before completing demonstration evidence") from exc
        if process.returncode != expected:
            raise ValueError(f"CLI returned {process.returncode}; expected {expected}: {process.stderr.strip()}")

    for name, format, suffix, expected in (("smoke", "json", "json", 0),
                                           ("faults", "junit", "xml", 1),
                                           ("recovery", "protobuf", "pb", 0)):
        execute([ROOT / f"scenarios/{name}.yaml", "--report-format", format,
                 "--report", scenario_dir / f"{name}.{suffix}", "--quiet"], expected)
    demonstrations = []
    for name, expected in (("recovery", True), ("faults", False)):
        before = set(output.glob("*/batch.json"))
        execute(["--plan", ROOT / f"plans/{name}.yaml", "--workers", workers,
                 "--qualification-policy", ROOT / "policies/strict.yaml", "--report-dir", output,
                 "--report-format", "protobuf", "--quiet"], 0 if expected else 1)
        manifests = set(output.glob("*/batch.json")) - before
        if len(manifests) != 1:
            raise ValueError("Expected one new batch manifest")
        manifest = manifests.pop()
        batch = json.loads(manifest.read_text())
        qualification_path = manifest.parent / "qualification.json"
        evidence = json.loads(qualification_path.read_text())
        if (not evidence["complete_evidence"] or evidence["qualified"] != expected
                or (batch["status"] == "passed") != expected):
            raise ValueError(f"Unexpected {name} demonstration outcome; inspect exported evidence")
        demonstrations.append({
            "example": name, "execution_status": batch["status"],
            "scenario_reports": str(scenario_dir), "manifest": str(manifest), "qualification_report": str(qualification_path),
            "decision": evidence["decision"], "observed": evidence["observed"],
            "criteria": evidence["criteria"], "failure_reasons": evidence["failure_reasons"],
            "execution_references": evidence["execution_references"],
        })
    try:
        validate_examples(output, relative_examples(output, demonstrations))
    except (ValueError, OSError, KeyError, TypeError, AttributeError, ParseError) as exc:
        raise ValueError("Demonstration evidence is missing or inconsistent; inspect exported reports") from exc
    return demonstrations


def relative_examples(output, examples):
    """Keep artifact paths portable while leaving the interactive demo paths intact."""
    return [{**example, **{key: str(Path(example[key]).relative_to(output))
                          for key in ("manifest", "qualification_report", "scenario_reports")}}
            for example in examples]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=Path("reports/demo"))
    parser.add_argument("--workers", type=int, choices=range(1, MAX_WORKERS + 1), default=2)
    args = parser.parse_args()
    try:
        results = demonstrate(args.output_dir, args.workers)
    except (ValueError, OSError, KeyError, TypeError, AttributeError, ParseError) as exc:
        parser.exit(2, f"Demo failed: {exc}\n")
    print(json.dumps({"scope": "simulated_software_tests", "demonstrations": results}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
