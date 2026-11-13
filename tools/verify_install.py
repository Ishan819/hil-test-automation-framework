"""Build a wheel and exercise its entry point in an isolated temporary environment."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import venv

ROOT = Path(__file__).resolve().parents[1]


def verify():
    with tempfile.TemporaryDirectory(prefix="hil-install-") as directory:
        work = Path(directory)
        env = os.environ.copy()
        env.pop("PYTHONPATH", None)
        env.pop("PYTHONHOME", None)
        def run(*command, environment=None, **options):
            return subprocess.run(command, cwd=work, env=env if environment is None else environment,
                                  check=True, **options)
        run(sys.executable, "-m", "pip", "wheel", "--no-deps", "--wheel-dir", str(work), str(ROOT))
        wheel, = work.glob("*.whl")
        venv.create(work / "env", with_pip=True)
        python = work / "env/bin/python"
        cli = work / "env/bin/hil-run"
        run(str(python), "-m", "pip", "install", str(wheel))
        run(str(python), "-m", "pip", "check")
        expected_version = run(str(python), "-c", "from importlib.metadata import version; "
                               "print(version('hil-test-automation-framework'))",
                               capture_output=True, text=True).stdout.strip()
        actual_version = run(str(cli), "--version", capture_output=True, text=True).stdout.strip()
        if actual_version != f"hil-run {expected_version}":
            raise RuntimeError("Installed CLI version does not match wheel metadata")
        run(str(cli), "--help")
        # Python-only installs must work without optional native tools on PATH.
        run(str(cli), "--doctor", environment={**env, "PATH": str(python.parent)})
        run(str(cli), str(ROOT / "scenarios/smoke.yaml"), "--quiet", "--report", str(work / "smoke.json"))
        smoke = json.loads((work / "smoke.json").read_text())
        if smoke["failed"] != 0 or smoke["passed"] != 3:
            raise RuntimeError("Installed smoke execution did not produce the expected results")
        run(str(cli), str(ROOT / "scenarios/smoke.yaml"), "--quiet", "--report-format", "protobuf",
            "--report", str(work / "smoke.pb"))
        run(str(python), "-c", "from pathlib import Path; import hil_automation; "
            "from hil_automation.protobuf import parse_result; "
            "installed = Path(hil_automation.__file__).is_relative_to(Path('env').resolve()); "
            "valid = parse_result(Path('smoke.pb').read_bytes()).summary.passed == 3; "
            "raise SystemExit(0 if installed and valid else 'Wheel import or Protobuf verification failed')")
        run(str(python), str(ROOT / "tools/demo_release.py"), "--workers", "2",
            "--output-dir", str(work / "demo"))
    print("Clean wheel installation verified (dependencies, version, Python-only doctor, JSON, Protobuf and release demo).")


if __name__ == "__main__":
    verify()
