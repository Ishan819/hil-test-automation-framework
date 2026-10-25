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
