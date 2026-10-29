"""Generate tracked Python bindings using the exact supported protoc version."""
import argparse
from pathlib import Path
import subprocess
import tempfile


ROOT = Path(__file__).resolve().parents[1]
VERSION = "libprotoc 33.6"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--protoc", default="protoc", help="Path to protoc 33.6")
    parser.add_argument("--check", action="store_true", help="Check tracked bindings without editing")
    args = parser.parse_args()
    version = subprocess.run(
        [args.protoc, "--version"], capture_output=True, text=True, check=True,
    ).stdout.strip()
    if version != VERSION:
        parser.error(f"Expected {VERSION}, found {version}")
    destination = ROOT / "src/hil_automation/proto/hil_results_pb2.py"
    with tempfile.TemporaryDirectory(prefix="hil-proto-gen-") as directory:
        subprocess.run([
            args.protoc, f"--proto_path={ROOT / 'proto'}",
            f"--python_out={directory}", str(ROOT / "proto/hil_results.proto"),
        ], check=True)
        content = (Path(directory) / "hil_results_pb2.py").read_bytes()
        if args.check:
            if not destination.exists() or destination.read_bytes() != content:
                parser.error("Tracked Protobuf bindings are stale; regenerate them")
        else:
            destination.write_bytes(content)


if __name__ == "__main__":
    main()
