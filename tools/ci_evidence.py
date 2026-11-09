"""Generate reproducible software-only CI evidence using the release demonstration."""
import argparse
import json
import os
from pathlib import Path

from demo_release import demonstrate


def generate(output):
    output = Path(output).resolve()
    if output.exists() and any(output.iterdir()):
        raise ValueError("Evidence directory must be empty")
    examples = demonstrate(output, 2)
    for example in examples:
        for key in ("manifest", "qualification_report", "scenario_reports"):
            example[key] = str(Path(example[key]).relative_to(output))
    (output / "index.json").write_text(json.dumps({"demonstrations": examples}, indent=2) + "\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["generate", "validate", "summary"])
    parser.add_argument("--output-dir", type=Path, default=Path("reports/ci-evidence"))
    parser.add_argument("--summary-file", type=Path, default=os.environ.get("GITHUB_STEP_SUMMARY"))
    parser.add_argument("--artifact-name", default="ci-test-evidence")
    args = parser.parse_args()
    try:
        if args.command == "generate":
            generate(args.output_dir)
        else:
            from validate_ci_evidence import validate
            examples = validate(args.output_dir)
            if args.command == "summary":
                from validate_ci_evidence import summary
                if args.summary_file is None:
                    raise ValueError("A summary file is required")
                with args.summary_file.open("a", encoding="utf-8") as stream:
                    stream.write(summary(examples, args.artifact_name))
    except (ValueError, OSError, KeyError, TypeError, AttributeError) as exc:
        if args.command == "summary" and args.summary_file is not None:
            with args.summary_file.open("a", encoding="utf-8") as stream:
                stream.write("## Simulated CI test evidence\n\nVerification: FAILED. Required evidence is missing or inconsistent. Inspect the evidence artifact and failed steps.\n")
        parser.exit(2, f"CI evidence generation failed: {type(exc).__name__}\n")


if __name__ == "__main__":
    main()
