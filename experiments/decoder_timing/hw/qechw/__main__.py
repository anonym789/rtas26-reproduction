"""Command line of the hardware decoder experiment; every setting comes from config.toml.

  python -m qechw [--config FILE] syndromes                           bivariate-bicycle syndromes of the runs
  python -m qechw [--config FILE] transfer [--only N ...] [--force]   Relay-BP work-counter transfer (CPU)
  python -m qechw [--config FILE] gpu [--only N ...] [--force]        Relay-BP on the GPU (CUDA-Q QEC)
  python -m qechw [--config FILE] mb-inputs                           Micro Blossom input from the CPU experiment's syndromes
  python -m qechw [--config FILE] mb-sim [--only N ...] [--dry-run]   simulation queues in the container (simulation host)
  python -m qechw [--config FILE] mb-collect                          simulation logs of the campaign -> per-shot tables
  python -m qechw [--config FILE] mb-calibrate                        board correction, validation, corrected rows
  python -m qechw [--config FILE] stats                               statistics of the campaign's raw/
  python -m qechw [--config FILE] sanity                              plausibility checks -> SANITY.md
  python -m qechw [--config FILE] check                               regenerate the recorded tables into paths.check and compare
  python -m qechw [--config FILE] config KEY                          print one setting (e.g. gpu.host)

--only takes the indices (from 0) of the runs or queues in config.toml that should run; default: all. Every command
writes into paths.output (check into paths.check); nothing is written into paths.data or paths.literature.
"""
from __future__ import annotations

import argparse
import shlex
import subprocess
import sys
from pathlib import Path

from .config import DEFAULT, load


def setting(cfg_path: Path, key: str) -> str:
    """A value of config.toml by dotted key, as plain text."""
    import tomllib
    with open(cfg_path, "rb") as f:
        v = tomllib.load(f)
    for part in key.split("."):
        v = v[part]
    return " ".join(str(x) for x in v) if isinstance(v, list) else str(v)


def queue_commands(cfg, only: list[int] | None = None) -> list[tuple[list[str], str]]:
    """(docker exec command, job list) of each Micro Blossom simulation queue, in the order of config.toml; the
    command writes the job list, given on its standard input, to queue_<prefix>.txt in the container."""
    mb = cfg.microblossom
    cmds = []
    for i, q in enumerate(mb.queues):
        if only is not None and i not in only:
            continue
        jobs = "".join(line + "\n" for block in q["jobs"] for line in mb.job_lines(block["d"], block["sources"]))
        name = f"queue_{q['prefix']}.txt"
        prep = ""
        if q.get("prep"):
            p = q["prep"]
            prep = f"./prep_slots.sh {p['from']} {q['prefix']} {q['slots']}"
            prep += f" {shlex.quote(p['map'])} && " if p.get("map") else " && "
        env = []
        if q.get("java_heap"):
            env.append(f"MB_JAVA_XMX={q['java_heap']}")
        if q["mode"] == "batch":
            env.append("SIM=/root/level2/run_sim_batch.sh")
        env.append(f"LOGDIR=/root/level2/{q['logs']}")
        script = f"cd /root/level2 && cat > {name} && {prep}{' '.join(env)} ./run_queue.sh {name} {q['slots']} {q['prefix']}"
        cmds.append((["docker", "exec", "-i", mb.container, "bash", "-lc", script], jobs))
    return cmds


def main() -> None:
    ap = argparse.ArgumentParser(prog="python -m qechw", description="Hardware decoders: FPGA, GPU, Micro Blossom.")
    ap.add_argument("--config", type=Path, default=DEFAULT, help="settings (default: %(default)s)")
    sub = ap.add_subparsers(dest="command", required=True)
    sub.add_parser("syndromes", help="bivariate-bicycle syndromes of the transfer and GPU runs")
    for name, text in (("transfer", "Relay-BP work-counter transfer"), ("gpu", "Relay-BP on the GPU")):
        p = sub.add_parser(name, help=text)
        p.add_argument("--only", type=int, nargs="*", default=None, help="indices of the runs in config.toml")
        p.add_argument("--force", action="store_true", help="rerun although the raw file exists")
    sub.add_parser("mb-inputs", help="Micro Blossom input from the CPU experiment's syndromes")
    sim = sub.add_parser("mb-sim", help="simulation queues inside the container")
    sim.add_argument("--only", type=int, nargs="*", default=None, help="indices of the queues in config.toml")
    sim.add_argument("--dry-run", action="store_true", help="print the commands only")
    sub.add_parser("mb-collect", help="simulation logs of the campaign -> per-shot tables")
    sub.add_parser("mb-calibrate", help="board correction of the simulation")
    sub.add_parser("stats", help="statistics of the campaign's raw/")
    sub.add_parser("sanity", help="plausibility checks")
    sub.add_parser("check", help="regenerate the recorded tables and compare")
    cf = sub.add_parser("config", help="print one setting")
    cf.add_argument("key")
    a = ap.parse_args()

    if a.command == "config":
        print(setting(a.config, a.key))
        return
    cfg = load(a.config)
    from .data import DataDir
    data = DataDir(cfg.output, cfg.campaign, cfg.literature)

    if a.command == "syndromes":
        from .syndromes import write_syndromes
        sc = cfg.syndromes
        write_syndromes(data.syndromes, sc.code, sc.d, sc.p, sc.shared_p, sc.shots)
    elif a.command in ("transfer", "gpu"):
        runs = cfg.transfer.runs if a.command == "transfer" else cfg.gpu.runs
        chosen = [runs[i] for i in a.only] if a.only is not None else runs
        if a.command == "transfer":
            from .transfer import transfer
            for run in chosen:
                transfer(data, cfg.relay, cfg.transfer, run, force=a.force)
        else:
            from .gpu import measure
            for run in chosen:
                measure(data, cfg.relay, cfg.gpu, run, fallback_syndromes=cfg.e2_syndromes, force=a.force)
    elif a.command == "mb-inputs":
        from .microblossom.convert import convert
        for c in cfg.microblossom.convert:
            print(convert(cfg.e2_syndromes, c["d"], c["p"], data.level2 / "inputs"))
    elif a.command == "mb-sim":
        for cmd, jobs in queue_commands(cfg, a.only):
            print(f"{shlex.join(cmd)}   # job list: {jobs.count(chr(10))} lines", flush=True)
            if not a.dry_run:
                subprocess.run(cmd, input=jobs, text=True, check=True)
    elif a.command == "mb-collect":
        from .microblossom.logs import collect
        for s in cfg.microblossom.collect:
            if collect(data.campaign_level2, data.level2, s, cfg.microblossom.freq_hz[s.d]) is None:
                print(f"skipped {s.source} d{s.d} {s.mode}{' ' + s.tag if s.tag else ''}: no complete chunk in {s.log_folder}/")
    elif a.command == "mb-calibrate":
        from .microblossom.calibrate import calibrate
        calibrate(data, cfg.microblossom)
    elif a.command == "stats":
        from .stats import write_stats
        write_stats(data)
    elif a.command == "sanity":
        from .sanity import write_report
        data.root.mkdir(parents=True, exist_ok=True)
        write_report(data, data.root / "SANITY.md")
    elif a.command == "check":
        from .check import check
        sys.exit(0 if check(data, cfg) else 1)


if __name__ == "__main__":
    sys.exit(main())
