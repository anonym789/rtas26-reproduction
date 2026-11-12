"""Command line of the network experiment; every setting comes from config.toml.

  python -m qecnet [--config FILE] load                     load/frame_sizes.csv
  python -m qecnet [--config FILE] bound                    bound/*.csv
  python -m qecnet [--config FILE] simulate SET [--workers W] [--match REGEX]
                                                            sim/raw for SET in checks, s1, s3, edge
  python -m qecnet [--config FILE] stats                    sim/stats/*.csv from the runs in paths.runs
  python -m qecnet [--config FILE] sanity                   the plausibility checks, SANITY.md
  python -m qecnet [--config FILE] check                    regenerate the recorded tables into paths.check and compare

Every command writes into paths.output (check into paths.check); nothing is written into paths.data.
"""
from __future__ import annotations

import argparse
import multiprocessing as mp
import os
import sys
from pathlib import Path


def main() -> None:
    # the settings are read when the package's modules are imported, so --config takes effect first
    pre = argparse.ArgumentParser(add_help=False)
    pre.add_argument("--config", type=Path)
    known, _ = pre.parse_known_args()
    if known.config:
        os.environ["QECNET_CONFIG"] = str(known.config.resolve())

    from . import parameters as P
    from .data import DataDir
    from .jobs import JOB_SETS

    ap = argparse.ArgumentParser(prog="python -m qecnet", description="The syndrome network under load.")
    ap.add_argument("--config", type=Path, help=f"settings file (default: {P.CONFIG})")
    sub = ap.add_subparsers(dest="command", required=True)
    sub.add_parser("load", help="frame sizes of the load model")
    sub.add_parser("bound", help="network-calculus bounds, crossings, R x L grid, saturation")
    sim = sub.add_parser("simulate", help="simulate one job set")
    sim.add_argument("set", choices=list(JOB_SETS))
    sim.add_argument("--workers", type=int, default=P.WORKERS or max(1, mp.cpu_count() - 2))
    sim.add_argument("--match", default=None, help="only configurations whose id matches this regular expression")
    sub.add_parser("stats", help="statistics of the simulation runs")
    sub.add_parser("sanity", help="plausibility checks")
    sub.add_parser("check", help="regenerate the recorded tables and compare")
    a = ap.parse_args()
    data = DataDir(P.OUTPUT, P.RUNS)

    if a.command == "load":
        from .frames import ethernet_floor, frame_size_table
        data.load.mkdir(parents=True, exist_ok=True)
        df = frame_size_table()
        df.to_csv(data.load / "frame_sizes.csv", index=False)
        print(f"wrote {data.load / 'frame_sizes.csv'} ({len(df)} rows)")
        print("84 B floor holds up to:", ethernet_floor())
    elif a.command == "bound":
        from .bounds import write_bounds
        write_bounds(data)
    elif a.command == "simulate":
        from .runner import simulate
        simulate(data, a.set, a.workers, a.match)
    elif a.command == "stats":
        from .stats import write_stats
        write_stats(data)
    elif a.command == "sanity":
        from .sanity import write_report
        write_report(data, data.root / "SANITY.md")
    elif a.command == "check":
        from .check import check
        sys.exit(0 if check(P.DATA, P.CHECK) else 1)


if __name__ == "__main__":
    main()
