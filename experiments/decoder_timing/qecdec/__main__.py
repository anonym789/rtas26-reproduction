"""Command line of the decoder timing experiment; every setting comes from config.toml.

  python -m qecdec [--config FILE] syndromes [--code ...] [--d ...] [--p ...] [--force] [--outdir DIR] [--seed-offset N]
  python -m qecdec [--config FILE] graphs [--d ...] [--p ...]      fusion-blossom graphs of the surface-code DEMs
  python -m qecdec [--config FILE] measure --decoder DEC --code CODE --d D --p P [--core C] [--reps R] [--shots N]
                                           [--subdir S] [--syndromes DIR] [--force]
  python -m qecdec [--config FILE] jobs {native,python,anchor,stability}   jobs of the campaign, one per line
  python -m qecdec [--config FILE] queue --cores LIST --jobs FILE [--log-dir DIR]
  python -m qecdec cores --n N --socket S [--exclude LIST]          the quietest L3 complexes, one core each
  python -m qecdec [--config FILE] [--campaign DIR] stats            statistics of the campaign
  python -m qecdec [--config FILE] [--campaign DIR] sanity [--anchor-only]   the plausibility checks, SANITY.md
  python -m qecdec [--config FILE] check                            regenerate the recorded statistics into paths.check and compare
  python -m qecdec [--config FILE] config KEY                       print one setting (paths resolved)

Every command writes into paths.output (check into paths.check). --campaign overrides paths.campaign.
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path


def setting(key: str) -> str:
    """A value of the settings file by dotted key, as plain text; paths are resolved."""
    from . import parameters as P
    v = P.SETTINGS
    for part in key.split("."):
        v = v[part]
    if key.startswith("paths."):
        return str((P.CONFIG.parent / v).resolve())
    if isinstance(v, bool):
        return "true" if v else "false"
    return " ".join(str(x) for x in v) if isinstance(v, list) else str(v)


def main() -> None:
    # the settings are read when the package's modules are imported, so --config and --campaign take effect first
    pre = argparse.ArgumentParser(add_help=False)
    pre.add_argument("--config", type=Path)
    pre.add_argument("--campaign", type=Path)
    known, _ = pre.parse_known_args()
    if known.config:
        os.environ["QECDEC_CONFIG"] = str(known.config.resolve())
    if known.campaign:
        os.environ["QECDEC_CAMPAIGN"] = str(known.campaign.resolve())

    from . import parameters as P
    from .data import DataDir

    ap = argparse.ArgumentParser(prog="python -m qecdec", description="Timing of QEC decoders.")
    ap.add_argument("--config", type=Path, help=f"settings file (default: {P.CONFIG})")
    ap.add_argument("--campaign", type=Path, help=f"campaign the statistics and checks read (default: {P.CAMPAIGN})")
    sub = ap.add_subparsers(dest="command", required=True)

    syn = sub.add_parser("syndromes", help="circuits, DEMs and sampled detection events")
    syn.add_argument("--code", nargs="*", default=P.CODES)
    syn.add_argument("--d", type=int, nargs="*", default=None)
    syn.add_argument("--p", type=float, nargs="*", default=P.ERROR_RATES)
    syn.add_argument("--force", action="store_true")
    syn.add_argument("--outdir", type=Path, default=None, help="another folder (seed check)")
    syn.add_argument("--seed-offset", type=int, default=0)

    gr = sub.add_parser("graphs", help="fusion-blossom graphs of the surface-code DEMs")
    gr.add_argument("--d", type=int, nargs="*", default=P.DISTANCES["surface"])
    gr.add_argument("--p", type=float, nargs="*", default=P.ERROR_RATES)

    me = sub.add_parser("measure", help="time one decoder on one grid point")
    me.add_argument("--decoder", required=True, choices=P.DECODERS)
    me.add_argument("--code", required=True, choices=P.CODES)
    me.add_argument("--d", type=int, required=True)
    me.add_argument("--p", type=float, required=True)
    me.add_argument("--core", type=int, default=None)
    me.add_argument("--reps", type=int, default=None, help="default: 3 (1 for the BB code)")
    me.add_argument("--shots", type=int, default=0, help="limit shots (0 = all sampled)")
    me.add_argument("--subdir", default=None, help="write under raw/<subdir>/ (stability, seedcheck)")
    me.add_argument("--syndromes", type=Path, default=None)
    me.add_argument("--force", action="store_true")

    jo = sub.add_parser("jobs", help="the campaign's jobs, one `decoder code d p` per line")
    jo.add_argument("kind", choices=["native", "python", "anchor", "stability"])

    qu = sub.add_parser("queue", help="run jobs in parallel, one pinned core each")
    qu.add_argument("--cores", required=True)
    qu.add_argument("--jobs", required=True, type=Path)
    qu.add_argument("--log-dir", type=Path, default=None)

    co = sub.add_parser("cores", help="the quietest L3 complexes, one core each")
    co.add_argument("--n", type=int, default=12)
    co.add_argument("--socket", type=int, default=1)
    co.add_argument("--cores-per-socket", type=int, default=64)
    co.add_argument("--l3-size", type=int, default=4)
    co.add_argument("--sample", type=float, default=5.0)
    co.add_argument("--exclude", default="", help="comma list of cores to keep free (e.g. the measurement core)")

    sub.add_parser("stats", help="statistics and pWCET fits")
    sa = sub.add_parser("sanity", help="plausibility checks")
    sa.add_argument("--anchor-only", action="store_true")
    sub.add_parser("check", help="regenerate the recorded statistics and compare")
    cf = sub.add_parser("config", help="print one setting")
    cf.add_argument("key")
    a = ap.parse_args()
    if a.command == "config":
        print(setting(a.key))
        return
    data = DataDir(P.OUTPUT, P.CAMPAIGN)

    if a.command == "syndromes":
        from .grid import GridPoint
        from .syndromes import generate, update_index
        outdir = a.outdir or data.syndromes
        rows = []
        for code in a.code:
            for d in (a.d or P.DISTANCES[code]):
                for p in a.p:
                    r = generate(GridPoint(code, d, p), outdir, a.force, a.seed_offset)
                    rows.append(r)
                    print(f"{code:7s} d={d:2d} p={p:g} qubits={r['num_qubits']:4d} dets={r['num_detectors']:6d} "
                          f"errors={r['num_errors']:7d} obs={r['num_observables']} shots={r['shots']} "
                          f"mean_ndet={r['mean_n_detections']:.1f}", flush=True)
        update_index(outdir, rows)
    elif a.command == "graphs":
        from .fbgraph import write_graph
        from .grid import GridPoint
        for d in a.d:
            for p in a.p:
                point = GridPoint("surface", d, p)
                g = write_graph(data.syndromes, point)
                print(f"{point.name}: vertices={g['vertex_num']} edges={len(g['weighted_edges'])} "
                      f"virtual={len(g['virtual_vertices'])}", flush=True)
    elif a.command == "measure":
        from .grid import GridPoint
        from .measure import measure
        measure(data, a.decoder, GridPoint(a.code, a.d, a.p), core=a.core, reps=a.reps, shots=a.shots,
                subdir=a.subdir, syndromes=a.syndromes, force=a.force)
    elif a.command == "jobs" and a.kind == "anchor":
        A = P.ANCHOR
        print(A["decoder"], A["code"], A["d"], A["p"])
    elif a.command == "jobs" and a.kind == "stability":
        for dec, code, d, p in P.STABILITY_POINTS:
            print(dec, code, d, p)
    elif a.command == "jobs":
        from .grid import all_jobs
        jobs = [(dec, pt) for dec, pt in all_jobs() if (dec in P.NATIVE_DECODERS) == (a.kind == "native")]
        if a.kind == "python":   # longest first: the BB code, then large distances
            jobs.sort(key=lambda j: (-(j[1].code == "bb"), -j[1].d))
        for dec, pt in jobs:
            print(dec, pt.code, pt.d, pt.p)
    elif a.command == "queue":
        from .hosttools import run_queue
        cores = [int(c) for c in a.cores.split(",")]
        sys.exit(1 if run_queue(cores, a.jobs, a.log_dir or data.raw / "logs") else 0)
    elif a.command == "cores":
        from .hosttools import quietest_cores
        exclude = {int(c) for c in a.exclude.split(",") if c}
        print(",".join(str(c) for c in quietest_cores(a.n, a.socket, a.cores_per_socket, a.l3_size, a.sample, exclude)))
    elif a.command == "stats":
        from .stats import write_stats
        write_stats(data)
    elif a.command == "sanity":
        from .sanity import write_report
        data.root.mkdir(parents=True, exist_ok=True)
        ok = write_report(data, data.root / "SANITY.md", a.anchor_only)
        if a.anchor_only:
            sys.exit(0 if ok else 1)
    elif a.command == "check":
        from .check import check
        sys.exit(0 if check(data, P.DATA, P.CHECK) else 1)


if __name__ == "__main__":
    main()
