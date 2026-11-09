"""Check CI evidence against configured inventories and existing serializers."""
import json
from pathlib import Path
from xml.etree import ElementTree as ET

from hil_automation.config import load_suite
from hil_automation.orchestration import BatchReport, SuiteExecution
from hil_automation.plans import load_plan
from hil_automation.protobuf import parse_result, report_to_proto
from hil_automation.qualification import evaluate_qualification
from hil_automation.qualification_policy import load_policy
from hil_automation.runner import AttemptResult, CaseResult, RunReport, StepResult

ROOT = Path(__file__).resolve().parents[1]


def require(condition):
    if not condition:
        raise ValueError("Missing or inconsistent CI evidence")


def child(directory, name):
    path = (directory / name).resolve()
    require(path.is_relative_to(directory.resolve()) and path.is_file())
    return path


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def restore(payload):
    data = dict(payload)
    for key in ("metadata", "retry_summary", "statistics", "action_statistics"):
        data.pop(key)
    cases = []
    for item in data.pop("results"):
        case = dict(item)
        case.pop("retry_count")
        case.pop("passed_after_retry")
        case["steps"] = [StepResult(**step) for step in case["steps"]]
        case["attempts"] = [AttemptResult(**{**attempt, "steps": [StepResult(**step) for step in attempt["steps"]]})
                            for attempt in case["attempts"]]
        cases.append(CaseResult(**case))
    report = RunReport(**data, results=cases)
    require(report.to_dict() == payload)
    return report


def validate(output):
    output = Path(output).resolve()
    examples = read(child(output, "index.json"))["demonstrations"]
    require([item["example"] for item in examples] == ["recovery", "faults"])
    seen = set()
    for example in examples:
        name = example["example"]
        manifest = child(output, example["manifest"])
        payload = read(manifest)
        plan = load_plan(ROOT / f"plans/{name}.yaml")
        executions = []
        clean = dict(payload)
        clean["suites"] = []
        for item in payload["suites"]:
            report = restore(item["report"])
            require(report.run_id not in seen)
            seen.add(report.run_id)
            require(parse_result(child(manifest.parent, item["report_file"]).read_bytes()) == report_to_proto(report))
            executions.append(SuiteExecution(item["suite"], item["planned_cases"], report, item["error"]))
            clean["suites"].append({key: value for key, value in item.items() if key != "report_file"})
        batch = BatchReport(payload["plan"], executions, payload["started_at"], payload["finished_at"],
                            payload["duration_ms"], run_id=payload["run_id"], workers=payload["workers"])
        require(batch.run_id not in seen)
        seen.add(batch.run_id)
        require(batch.to_dict() == clean)
        qualification = read(child(output, example["qualification_report"]))
        require(child(output, example["qualification_report"]).parent == manifest.parent)
        actual = evaluate_qualification(batch, load_policy(ROOT / "policies/strict.yaml"), expected=plan).to_dict()
        # Evaluation time is independent of execution; all substantive fields must match.
        actual["evaluated_at"] = qualification["evaluated_at"]
        require(actual == qualification and actual["complete_evidence"])
        require(actual["qualified"] is (name == "recovery"))
        require(batch.status == ("passed" if name == "recovery" else "failed"))
        for key in ("decision", "observed", "criteria", "failure_reasons", "execution_references"):
            require(example[key] == actual[key])
        require(example["execution_status"] == batch.status)
    # Independently check the three single-suite formats emitted by the demo.
    require(examples[0]["scenario_reports"] == examples[1]["scenario_reports"])
    scenario = output / examples[0]["scenario_reports"]
    smoke = restore(read(child(scenario, "smoke.json")))
    require(evaluate_qualification(smoke, load_policy(ROOT / "policies/strict.yaml"),
                                  expected=load_suite(ROOT / "scenarios/smoke.yaml")).qualified)
    faults = ET.parse(child(scenario, "faults.xml")).getroot()
    expected = load_suite(ROOT / "scenarios/faults.yaml")
    require(faults.tag == "testsuite" and faults.get("name") == expected.name and bool(faults.get("id")))
    require([case.get("name") for case in faults] == [case.name for case in expected.tests])
    require(faults.get("tests") == "2" and faults.get("failures") == "2" and faults.get("errors") == "0")
    require(all(case.find("failure") is not None and case.get("classname") == expected.name for case in faults))
    recovery = parse_result(child(scenario, "recovery.pb").read_bytes())
    expected = load_suite(ROOT / "scenarios/recovery.yaml")
    require(recovery.suite == expected.name and [case.name for case in recovery.cases] == [case.name for case in expected.tests])
    require(recovery.summary.passed == len(expected.tests) and recovery.summary.failed == 0)
    return examples


def safe_text(value):
    """Render bounded plain text: encode Markdown, HTML and control characters."""
    value = " ".join(str(value).split())[:400]
    return "".join(char if char.isascii() and (char.isalnum() or char == " ")
                   else f"&#{ord(char)};" for char in value)


def summary(examples, artifact_name):
    lines = ["## Simulated CI test evidence", "",
             "Verification: passed. The faults example is an explicitly validated expected failure.", "",
             "| Example | Execution | Passed | Failed | Qualification |", "| --- | --- | ---: | ---: | --- |"]
    for item in examples:
        metrics = item["observed"]
        lines.append("| " + " | ".join(safe_text(value) for value in (
            item["example"], item["execution_status"], metrics["passed_cases"],
            metrics["failed_cases"], item["decision"])) + " |")
    lines.extend(["", "Qualification failure reasons:"])
    for item in examples:
        for reason in item["failure_reasons"]:
            lines.append(f"- {safe_text(item['example'])}: {safe_text(reason)}")
    lines.extend(["", f"Evidence artifact: {safe_text(artifact_name)} (this run's Artifacts section).",
                  "Contains index.json, batch.json, qualification.json and JSON/JUnit/Protobuf suite reports.", ""])
    return "\n".join(lines)
