"""L1 in one command: the manifest for the given months, then every parser, in order.

    python -m src.clean.l1 202405 202507 202508

Each step runs as its own process (python -m src.clean.<step>); the first one that fails stops
the run. List every month you want, old and new: the manifest and the checks written by the
parsers are rewritten (see src.clean.manifest). The row checks (s1_rows, *_checks) are not run.

Read by month (the bundles of the manifest): S1, S9, S3, S13, S11, S7, S12.
Read whole, whatever the months: S2 / S10 / S14 and S6 (every version), S4 / S5 and S8 (one file
each).
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import time

STEPS = [
    ["manifest"],  # followed by the months
    ["s1_periods", "--source", "s1"], ["s1_parse", "--source", "s1"],
    ["s1_periods", "--source", "s9"], ["s1_parse", "--source", "s9"],
    ["s3_parse"], ["s13_parse"], ["s11_parse"], ["s7_parse"], ["s12_parse"],
    ["versions_parse"], ["s6_parse"], ["signals_parse"], ["s8_parse"],
]


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("months", nargs="+", help="YYYYMM, e.g. 202405")
    args = ap.parse_args()
    start = time.time()
    for step in STEPS:
        cmd = [sys.executable, "-m", f"src.clean.{step[0]}", *step[1:],
               *(args.months if step[0] == "manifest" else [])]
        print(f"== {' '.join(cmd[2:])}", flush=True)
        t = time.time()
        subprocess.run(cmd, check=True)
        print(f"== {step[0]} done in {time.time() - t:.0f} s", flush=True)
    print(f"L1 done in {(time.time() - start) / 60:.1f} min")


if __name__ == "__main__":
    main()
