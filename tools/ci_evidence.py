"""Generate reproducible software-only CI evidence using the release demonstration."""
import argparse
import json
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
    parser.add_argument("command", choices=["generate"])
    parser.add_argument("--output-dir", type=Path, default=Path("reports/ci-evidence"))
    args = parser.parse_args()
    try:
        generate(args.output_dir)
    except (ValueError, OSError) as exc:
        parser.exit(2, f"CI evidence generation failed: {type(exc).__name__}\n")


if __name__ == "__main__":
    main()
