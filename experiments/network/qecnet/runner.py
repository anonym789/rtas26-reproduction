"""Runs a job set in parallel, one configuration per process, and writes one raw file per configuration.

Raw file sim/raw[/checks, /edge]/<stem>.csv.gz: one row per recorded cycle. Metadata meta/<stem>.json:
cycles, seed, wall time, per-port offered load and largest queue. Configurations whose raw file exists
are skipped, so an interrupted run resumes.
"""
from __future__ import annotations

import json
import multiprocessing as mp
import re
import sys
import time
from pathlib import Path

import pandas as pd
import simpy

from . import simulation
from .configuration import Config
from .data import DataDir
from .jobs import JOB_SETS, cycles


def run_one(job: tuple[Config, Path]) -> tuple[str, float, str]:
    cfg, folder = job
    raw = folder / f"{cfg.file_stem}.csv.gz"
    if raw.exists():
        return cfg.config_id, 0.0, "skipped"
    warmup, recorded = cycles(cfg)
    res = simulation.run(cfg, warmup, recorded)
    ln = cfg.link_spec
    pc = res["per_cycle"]
    df = pd.DataFrame(dict(
        config_id=cfg.config_id, topology=cfg.topology, link=cfg.link, link_rate_bps=ln.payload_rate_bps,
        hop_latency_ns=ln.latency_ns, scenario=cfg.scenario_label, frame_bits=pc["frame_bits"],
        aggregation=cfg.agg, Q_c=cfg.q_c, q=cfg.q_c // 2, N=cfg.n, cycle_ns=cfg.cycle_ns, cycle=pc["cycle"],
        round_completion_ns=pc["round_completion_ns"], max_queue_frames=pc["max_queue_frames"],
        utilisation=pc["utilisation"], seed=cfg.seed, burst=pc["burst"]))
    (folder / "meta").mkdir(parents=True, exist_ok=True)
    meta = dict(config_id=cfg.config_id, seed=cfg.seed, k=cfg.fan_in, python=sys.version.split()[0],
                simpy=simpy.__version__, **res["meta"], ports=res["ports"])
    tmp = raw.with_suffix(".tmp.gz")
    df.to_csv(tmp, index=False, float_format="%.6f", compression="gzip")
    (folder / "meta" / f"{cfg.file_stem}.json").write_text(json.dumps(meta, indent=1))
    tmp.rename(raw)  # the raw file appears only when complete
    return cfg.config_id, res["meta"]["wall_s"], "done"


def simulate(data: DataDir, set_name: str, workers: int, match: str | None = None) -> None:
    job_set = JOB_SETS[set_name]
    jobs = job_set.jobs()
    if match:
        jobs = [j for j in jobs if re.search(match, j.config_id)]
    folder = data.new_runs_folder(job_set.folder)
    folder.mkdir(parents=True, exist_ok=True)
    jobs.sort(key=lambda c: -c.n * sum(cycles(c)))  # longest first
    t0 = time.time()
    print(f"{set_name}: {len(jobs)} configurations on {workers} workers", flush=True)
    with mp.Pool(workers, maxtasksperchild=1) as pool:
        for i, (cid, wall, status) in enumerate(pool.imap_unordered(run_one, [(j, folder) for j in jobs]), 1):
            print(f"[{i}/{len(jobs)} {time.time() - t0:7.0f}s] {status:7s} {wall:8.1f}s {cid}", flush=True)
