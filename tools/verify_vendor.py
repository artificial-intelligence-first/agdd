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
        path=ROOT / "agdd" / "assets" / "contracts" / "agent.schema.json",
        digest="52ffe35c1e09cd9d698770cfe17615caf4589333cc48f9ad296aeb1d8e697636",
    ),
    VendoredFile(
        path=ROOT / "agdd" / "assets" / "contracts" / "flow_summary.schema.json",
        digest="c4b339e16065caa21e4be2bf672cade426b42a9bb5ef6cb4dfc7ee4b0c5ff8aa",
    ),
    VendoredFile(
        path=ROOT / "agdd" / "assets" / "policies" / "flow_governance.yaml",
        digest="e1d1db8af41cdc3cf913538551d42af6b07e809b7c814bce40c223fd76a12b06",
    ),
    VendoredFile(
        path=ROOT / "examples" / "flowrunner" / "prompt_flow.yaml",
        digest="bae697ff9ebf582af28579eb0443c8b1c80b4cbe6590d735d8cf5f1ca7be3f7b",
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
