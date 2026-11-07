"""Local, read-only availability checks; optional native tools are never executed."""
from dataclasses import dataclass
from importlib import import_module, metadata
import os
from pathlib import Path
import re
import shutil
import sys


DISTRIBUTION = "hil-test-automation-framework"


@dataclass(frozen=True)
class Check:
    name: str
    required: bool
    available: bool
    detail: str

    @property
    def status(self) -> str:
        return ("PASS" if self.available else "FAIL") if self.required else (
            "OPTIONAL PASS" if self.available else "OPTIONAL MISSING"
        )


def check_environment() -> list[Check]:
    """Check Python-only requirements separately from native development tools.

    Installed metadata carries pyproject.toml's Requires-Python value, including
    in wheel installs where the source configuration is unavailable.
    """
    checks = []
    try:
        requirement = metadata.metadata(DISTRIBUTION)["Requires-Python"]
        # The project currently declares a simple minimum version (>=3.10).
        minimum = re.fullmatch(r">=\s*(\d+)\.(\d+)(?:\.(\d+))?", requirement or "")
        if minimum is None:
            checks.append(Check("Python", True, False, "Cannot interpret installed Python requirement"))
        else:
            supported = tuple(sys.version_info[:3]) >= tuple(int(n or 0) for n in minimum.groups())
            checks.append(Check("Python", True, supported, f"Requires {requirement}"))
    except metadata.PackageNotFoundError:
        checks.append(Check("Python", True, False, "HIL Bench package metadata is missing"))

    for distribution, module in (("PyYAML", "yaml"), ("protobuf", "google.protobuf")):
        try:
            metadata.version(distribution)
            import_module(module)
        except Exception:
            # Import failures can contain local paths or arbitrary exception text.
            checks.append(Check(distribution, True, False, "Package missing or cannot be imported"))
        else:
            checks.append(Check(distribution, True, True, "Installed and importable"))
    try:
        import_module("hil_automation.proto.hil_results_pb2")
    except Exception:
        checks.append(Check("Protobuf bindings", True, False, "Bundled bindings cannot be imported"))
    else:
        checks.append(Check("Protobuf bindings", True, True, "Bundled Python bindings import successfully"))

    for name, commands, detail in (
        ("CMake", ("cmake",), "Native builds only; availability does not verify version"),
        ("C++ compiler", ("c++", "clang++", "g++"), "Native builds only; availability does not verify C++17 support"),
        ("protoc", ("protoc",), "Regeneration only; CMake builds its own pinned protoc"),
    ):
        checks.append(Check(name, False, any(shutil.which(command) for command in commands), detail))

    configured = os.environ.get("HIL_NATIVE_TEST_BINARY")
    available = False
    if configured:
        try:
            path = Path(configured)
            available = path.is_file() and os.access(path, os.X_OK)
        except (OSError, ValueError):
            pass
    checks.append(Check("Native test executable", False, available,
                        "Configured executable is available" if available else
                        "Configured executable is missing or not executable" if configured else
                        "HIL_NATIVE_TEST_BINARY is not configured"))
    return checks
