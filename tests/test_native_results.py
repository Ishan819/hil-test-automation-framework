from dataclasses import asdict

from hil_automation.native_results import NativeCaseResult


def test_native_case_model_serializes_with_existing_result_conventions():
    case = NativeCaseResult("Thermal", "Cools", "passed", 12.5)
    assert asdict(case) == {
        "suite": "Thermal", "name": "Cools", "status": "passed",
        "duration_ms": 12.5, "details": "",
    }
