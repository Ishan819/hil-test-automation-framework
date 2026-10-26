import sys

import pytest


@pytest.fixture
def native_executable(tmp_path):
    """Create a deterministic executable fixture for the macOS/Linux process boundary."""
    def create(source, name="native test binary"):
        path = tmp_path / name
        path.write_text(f"#!{sys.executable}\n{source}\n", encoding="utf-8")
        path.chmod(0o755)
        return path

    return create


@pytest.fixture
def gtest_executable(native_executable):
    def create(xml, exit_code=0):
        return native_executable(
            "import pathlib, sys\n"
            "output = pathlib.Path(next(arg.split('xml:', 1)[1] for arg in sys.argv "
            "if arg.startswith('--gtest_output=')))\n"
            + (f"output.write_text({xml!r}, encoding='utf-8')\n" if xml is not None else "")
            + "print('native output')\nprint('native diagnostic', file=sys.stderr)\n"
            + f"sys.exit({exit_code})"
        )

    return create
