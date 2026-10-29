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


def _compiled_binary(environment_key, filename):
    import os
    from pathlib import Path

    configured = os.environ.get(environment_key)
    path = Path(configured) if configured else (
        Path(__file__).resolve().parents[1] / "build" / "cpp" / filename
    )
    if not path.is_file():
        if configured:
            pytest.fail(f"{environment_key} does not identify a compiled binary: {path}")
        pytest.skip(f"Build {filename} to run native integration tests")
    return path.resolve()


@pytest.fixture
def compiled_gtest_binary():
    return _compiled_binary("HIL_NATIVE_TEST_BINARY", "hil_bench_tests")


@pytest.fixture
def compiled_reporting_binary():
    return _compiled_binary("HIL_NATIVE_REPORTING_BINARY", "hil_reporting_fixture")


@pytest.fixture
def compiled_proto_binary():
    return _compiled_binary("HIL_PROTO_EXCHANGE_BINARY", "hil_proto_exchange")
