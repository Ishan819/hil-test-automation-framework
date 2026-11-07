from pathlib import Path
import re
from types import SimpleNamespace

import pytest

from hil_automation import doctor


def test_configured_environment(monkeypatch, tmp_path):
    monkeypatch.setattr(doctor.metadata, "metadata", lambda _: {"Requires-Python": ">=3.10"})
    monkeypatch.setattr(doctor.metadata, "version", lambda _: "installed")
    monkeypatch.setattr(doctor, "import_module", lambda _: SimpleNamespace())
    monkeypatch.setattr(doctor.sys, "version_info", (3, 12, 0))
    monkeypatch.setattr(doctor.shutil, "which", lambda _: "/available/tool")
    native = tmp_path / "native"
    native.write_text("not executed")
    native.chmod(0o755)
    monkeypatch.setenv("HIL_NATIVE_TEST_BINARY", str(native))
    checks = doctor.check_environment()
    assert all(check.available for check in checks)
    assert [check.name for check in checks if check.required] == [
        "Python", "PyYAML", "protobuf", "Protobuf bindings",
    ]
    assert all(check.status == "PASS" for check in checks if check.required)
    assert all(check.status == "OPTIONAL PASS" for check in checks if not check.required)


@pytest.fixture
def python_environment(monkeypatch):
    monkeypatch.setattr(doctor.metadata, "metadata", lambda _: {"Requires-Python": ">=3.10"})
    monkeypatch.setattr(doctor.metadata, "version", lambda _: "installed")
    monkeypatch.setattr(doctor, "import_module", lambda _: SimpleNamespace())
    monkeypatch.setattr(doctor.sys, "version_info", (3, 12, 0))
    monkeypatch.setattr(doctor.shutil, "which", lambda _: None)
    monkeypatch.delenv("HIL_NATIVE_TEST_BINARY", raising=False)


@pytest.mark.parametrize("version, supported", [((3, 9, 9), False), ((3, 10, 0), True), ((3, 13, 0), True)])
def test_python_version_compatibility(python_environment, monkeypatch, version, supported):
    monkeypatch.setattr(doctor.sys, "version_info", version)
    check = doctor.check_environment()[0]
    assert check.available == supported and check.required


@pytest.mark.parametrize("distribution", ["PyYAML", "protobuf"])
def test_missing_required_distribution(python_environment, monkeypatch, distribution):
    def installed(name):
        if name == distribution:
            raise doctor.metadata.PackageNotFoundError("SECRET_VALUE")
        return "installed"
    monkeypatch.setattr(doctor.metadata, "version", installed)
    checks = doctor.check_environment()
    failed, = [check for check in checks if check.required and not check.available]
    assert failed.name == distribution and failed.status == "FAIL"
    assert "SECRET_VALUE" not in repr(checks)


@pytest.mark.parametrize("module", ["yaml", "google.protobuf", "hil_automation.proto.hil_results_pb2"])
def test_broken_imports_have_safe_diagnostics(python_environment, monkeypatch, module):
    def load(name):
        if name == module:
            raise RuntimeError("SECRET_VALUE")
        return SimpleNamespace()
    monkeypatch.setattr(doctor, "import_module", load)
    checks = doctor.check_environment()
    assert sum(check.required and not check.available for check in checks) == 1
    assert "SECRET_VALUE" not in repr(checks)


@pytest.mark.parametrize("requirement", [None, ">=3.10,<4", "invalid"])
def test_unrecognized_python_metadata_fails_explicitly(python_environment, monkeypatch, requirement):
    monkeypatch.setattr(doctor.metadata, "metadata", lambda _: {"Requires-Python": requirement})
    check = doctor.check_environment()[0]
    assert not check.available and "Cannot interpret" in check.detail


def test_missing_project_metadata(python_environment, monkeypatch):
    def missing(_):
        raise doctor.metadata.PackageNotFoundError("SECRET_VALUE")
    monkeypatch.setattr(doctor.metadata, "metadata", missing)
    check = doctor.check_environment()[0]
    assert not check.available and "metadata is missing" in check.detail


def test_optional_tools_do_not_fail_python_environment(python_environment):
    checks = doctor.check_environment()
    assert all(check.available for check in checks if check.required)
    assert all(check.status == "OPTIONAL MISSING" for check in checks if not check.required)


@pytest.mark.parametrize("kind", ["missing", "directory", "nonexecutable"])
def test_configured_native_executable_is_optional_and_private(python_environment, monkeypatch, tmp_path, kind):
    path = tmp_path / "SECRET_VALUE"
    if kind == "directory":
        path.mkdir()
    elif kind == "nonexecutable":
        path.write_text("not executable")
        path.chmod(0o644)
    monkeypatch.setenv("HIL_NATIVE_TEST_BINARY", str(path))
    checks = doctor.check_environment()
    native = checks[-1]
    assert not native.available and not native.required
    assert "Configured executable" in native.detail
    assert "SECRET_VALUE" not in repr(checks)


def test_python_requirement_matches_project_configuration():
    source = Path(__file__).resolve().parents[1] / "pyproject.toml"
    requirement = re.search(r'^requires-python = "([^"]+)"', source.read_text(), re.MULTILINE).group(1)
    assert doctor.metadata.metadata(doctor.DISTRIBUTION)["Requires-Python"] == requirement
