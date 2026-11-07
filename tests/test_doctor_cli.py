import sys

import pytest

from hil_automation import cli, doctor


@pytest.mark.parametrize("required, available, code, status", [
    (True, True, 0, "PASS"), (True, False, 2, "FAIL"),
    (False, False, 0, "OPTIONAL MISSING"),
])
def test_doctor_output_and_exit_code(monkeypatch, capsys, required, available, code, status):
    monkeypatch.setattr(doctor, "check_environment", lambda: [doctor.Check("component", required, available, "diagnostic")])
    monkeypatch.setattr(sys, "argv", ["hil-run", "--doctor"])
    assert cli.main() == code
    captured = capsys.readouterr()
    assert captured.out == f"[{status}] component: diagnostic\n"
    assert captured.err == ""


@pytest.mark.parametrize("options", [["missing.yaml"], ["--plan", "missing.yaml"],
                                     ["--report", "unused.json"], ["--native-tests", "unused"],
                                     ["--quiet"], ["--workers", "2"]])
def test_doctor_rejects_execution_options(monkeypatch, capsys, options):
    monkeypatch.setattr(sys, "argv", ["hil-run", "--doctor", *options])
    with pytest.raises(SystemExit) as result:
        cli.main()
    assert result.value.code == 2
    captured = capsys.readouterr()
    assert "--doctor cannot be combined" in captured.err and not captured.out


@pytest.mark.parametrize("module, component", [("yaml", "PyYAML"), ("google.protobuf", "protobuf")])
def test_doctor_starts_when_required_import_is_missing(tmp_path, module, component):
    import subprocess

    script = f'''
import sys
class BlockImport:
    def find_spec(self, fullname, path=None, target=None):
        if fullname == {module!r} or fullname.startswith({module!r} + "."):
            raise ModuleNotFoundError("SECRET_VALUE")
sys.meta_path.insert(0, BlockImport())
from hil_automation.cli import main
sys.argv = ["hil-run", "--doctor"]
raise SystemExit(main())
'''
    process = subprocess.run([sys.executable, "-c", script], cwd=tmp_path, capture_output=True, text=True)
    assert process.returncode == 2
    assert f"[FAIL] {component}:" in process.stdout
    assert "SECRET_VALUE" not in process.stdout and not process.stderr
    assert not list(tmp_path.iterdir())


def test_version_remains_usable_without_yaml(tmp_path):
    import subprocess
    from importlib.metadata import version

    script = '''
import sys
class BlockImport:
    def find_spec(self, fullname, path=None, target=None):
        if fullname == "yaml":
            raise ModuleNotFoundError("yaml")
sys.meta_path.insert(0, BlockImport())
from hil_automation.cli import main
sys.argv = ["hil-run", "--version"]
main()
'''
    process = subprocess.run([sys.executable, "-c", script], cwd=tmp_path, capture_output=True, text=True)
    assert process.returncode == 0
    assert process.stdout == f"hil-run {version('hil-test-automation-framework')}\n"
    assert not process.stderr
