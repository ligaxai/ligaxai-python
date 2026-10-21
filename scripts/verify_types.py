"""Fail unless ``pyright --verifytypes`` reports a completeness score at or above the floor.

Cross-platform replacement for an awk pipeline so the Makefile and the Windows CI runner
share one gate. Usage: ``python scripts/verify_types.py [--min 95]``.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys

PACKAGE = "base_project_module"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--min", type=float, default=95.0, help="minimum score in percent")
    args = parser.parse_args()

    proc = subprocess.run(
        ["pyright", "--verifytypes", PACKAGE, "--ignoreexternal", "--outputjson"],
        capture_output=True,
        text=True,
        check=False,
    )
    try:
        report = json.loads(proc.stdout)
    except json.JSONDecodeError:
        print(proc.stdout, proc.stderr, sep="\n")
        print("verify_types: pyright produced no JSON report")
        return 1

    score = float(report["typeCompleteness"]["completenessScore"]) * 100
    symbols = report["typeCompleteness"]
    print(
        f"verify_types: {PACKAGE} completeness {score:.1f}% "
        f"(exported {symbols['exportedSymbolCounts']['withKnownType']} known, "
        f"{symbols['exportedSymbolCounts']['withAmbiguousType']} ambiguous, "
        f"{symbols['exportedSymbolCounts']['withUnknownType']} unknown)"
    )
    if score < args.min:
        for diag in report.get("generalDiagnostics", []):
            print(f"  {diag.get('message')}")
        print(f"verify_types: FAIL — below {args.min:.0f}%")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
