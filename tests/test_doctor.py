from types import SimpleNamespace

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
