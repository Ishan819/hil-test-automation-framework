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
        def run(*command):
            subprocess.run(command, cwd=work, env=env, check=True)
        run(sys.executable, "-m", "pip", "wheel", "--no-deps", "--wheel-dir", str(work), str(ROOT))
        wheel, = work.glob("*.whl")
        venv.create(work / "env", with_pip=True)
        python = work / "env/bin/python"
        cli = work / "env/bin/hil-run"
        run(str(python), "-m", "pip", "install", str(wheel))
        run(str(cli), "--help")
        run(str(cli), str(ROOT / "scenarios/smoke.yaml"), "--quiet", "--report", str(work / "smoke.json"))
        assert json.loads((work / "smoke.json").read_text())["failed"] == 0
        run(str(cli), str(ROOT / "scenarios/smoke.yaml"), "--quiet", "--report-format", "protobuf",
            "--report", str(work / "smoke.pb"))
        run(str(python), "-c", "from pathlib import Path; import hil_automation; "
            "from hil_automation.protobuf import parse_result; "
            "assert Path(hil_automation.__file__).is_relative_to(Path('env').resolve()); "
            "assert parse_result(Path('smoke.pb').read_bytes()).summary.passed == 3")
    print("Clean wheel installation verified (JSON and Protobuf).")


if __name__ == "__main__":
    verify()
