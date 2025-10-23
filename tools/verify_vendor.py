"""Verify hashes for vendored Flow Runner assets."""
from __future__ import annotations

import hashlib
import sys
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class VendoredFile:
    path: Path
    digest: str

    def check(self) -> tuple[bool, str]:
        if not self.path.is_file():
            return False, f"missing {self.path}"

        content = self.path.read_bytes()
        actual = hashlib.sha256(content).hexdigest()
        if actual != self.digest:
            return False, f"hash mismatch for {self.path} (expected {self.digest}, got {actual})"
        return True, ""


ROOT = Path(__file__).resolve().parents[1]
VENDORED_FILES = (
    VendoredFile(
        path=ROOT / "src" / "agdd" / "assets" / "contracts" / "agent.schema.json",
        digest="52ffe35c1e09cd9d698770cfe17615caf4589333cc48f9ad296aeb1d8e697636",
    ),
    VendoredFile(
        path=ROOT / "src" / "agdd" / "assets" / "contracts" / "flow_summary.schema.json",
        digest="c4b339e16065caa21e4be2bf672cade426b42a9bb5ef6cb4dfc7ee4b0c5ff8aa",
    ),
    VendoredFile(
        path=ROOT / "src" / "agdd" / "assets" / "policies" / "flow_governance.yaml",
        digest="07c59641c256e2e9c149d604d1ee4a37747b735b332f573b72b4d01645a471a3",
    ),
    VendoredFile(
        path=ROOT / "examples" / "flowrunner" / "prompt_flow.yaml",
        digest="986c0a672f2d8e259a3857b1b876ae71fd92ea00a6f21e592f8edeea21898fe5",
    ),
)


def main() -> int:
    all_ok = True
    for item in VENDORED_FILES:
        ok, message = item.check()
        if not ok:
            print(f"ERROR: {message}")
            all_ok = False
    if all_ok:
        print("Vendor verification passed.")
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
