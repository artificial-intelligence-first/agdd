"""Governance gate for Flow Runner summaries (CLI wrapper)."""
from __future__ import annotations

import sys
from pathlib import Path

from agdd.governance.gate import evaluate


def main(summary_path: str, policy_path: str | None = None) -> int:
    summary = Path(summary_path)
    policy = Path(policy_path) if policy_path is not None else None
    issues = evaluate(summary, policy)
    if issues:
        print("GOVERNANCE GATE FAILED")
        for issue in issues:
            print(f"- {issue}")
        return 2

    print("GOVERNANCE GATE PASSED")
    return 0


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("usage: python tools/gate_flow_summary.py <summary.json> [policy.yaml]")
        sys.exit(1)

    summary_arg = sys.argv[1]
    policy_arg = sys.argv[2] if len(sys.argv) > 2 else None
    sys.exit(main(summary_arg, policy_arg))
