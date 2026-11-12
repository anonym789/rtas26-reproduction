"""Measure one decoder on one grid point and write the tidy raw file.

Raw file, one row per timed decode call:
    decoder,code,d,p,rounds,shot,rep,time_ns,cycles,n_detections,logical_error,
    logical_flips,bp_iterations,osd_triggered,timing_method
logical_error = 1 if any observable is mispredicted (per block); logical_flips = number of mispredicted
observables. osd_triggered = 1 if BP did not converge and the post-processor (OSD or LSD) ran.
Appended next to it: runs.csv (one row per run) and machine_snapshots.csv (one row per run and phase).
"""
from __future__ import annotations

import csv
import datetime as dt
import gzip
import time
from pathlib import Path

import numpy as np

from .data import DataDir
from .decoders import DECODERS, Skipped
from .grid import GridPoint
from .machine import snapshot
from .syndromes import load_b8, read_index

RAW_COLUMNS = ["decoder", "code", "d", "p", "rounds", "shot", "rep", "time_ns", "cycles",
               "n_detections", "logical_error", "logical_flips", "bp_iterations", "osd_triggered", "timing_method"]


def append_csv(path: Path, row: dict) -> None:
    new = not path.exists()
    with open(path, "a", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(row.keys()))
        if new:
            w.writeheader()
        w.writerow(row)


def measure(data: DataDir, decoder: str, point: GridPoint, core: int | None = None, reps: int | None = None,
            shots: int = 0, subdir: str | None = None, syndromes: Path | None = None, force: bool = False) -> None:
    reps = point.reps if reps is None else reps
    syndromes = syndromes or data.syndromes
    out = data.raw_file(decoder, point, subdir)
    if out.exists() and not force:
        print(f"exists, skipping: {out}")
        return
    idx = read_index(syndromes, point)
    rounds = int(idx["rounds"])
    run_id = f"{decoder}_{point.name}_{dt.datetime.now().strftime('%Y%m%dT%H%M%S')}"
    print(f"[{run_id}] core={core} reps={reps}", flush=True)
    base_row = dict(run_id=run_id, decoder=decoder, code=point.code, d=point.d, p=point.p, subdir=subdir or "")
    snap0 = snapshot(core)
    info: dict = {}
    t_wall0 = time.time()
    try:
        res = DECODERS[decoder].run(idx, syndromes, point, reps, shots, core, info)
    except Skipped as s:
        print(s.record["reason"], flush=True)
        append_csv(data.raw / "skipped.csv", s.record)
        return
    snap1 = snapshot(core)

    n = int(res.shot.max()) + 1
    obs = load_b8(syndromes / idx["obs_file"], int(idx["num_observables"]), n)
    obs_mask = np.zeros(n, dtype=np.int64)
    for k in range(obs.shape[1]):
        obs_mask |= obs[:, k].astype(np.int64) << k
    ndet = np.load(syndromes / idx["ndet_file"])[:n]
    shot = res.shot
    flips_mask = res.pred ^ obs_mask[shot]
    logical_error = (flips_mask != 0).astype(np.int64)
    logical_flips = np.array([bin(int(m)).count("1") for m in flips_mask], dtype=np.int64)
    cycles = res.cycles
    out.parent.mkdir(parents=True, exist_ok=True)
    tm = info["timing_method"]
    with gzip.open(out, "wt", newline="") as f:
        w = csv.writer(f)
        w.writerow(RAW_COLUMNS)
        bpi, osd = res.bp_iterations, res.osd_triggered
        for i in range(len(shot)):
            w.writerow([decoder, point.code, point.d, point.p, rounds, int(shot[i]), int(res.rep[i]), int(res.time_ns[i]),
                        "" if cycles[i] < 0 else int(cycles[i]), int(ndet[shot[i]]), int(logical_error[i]),
                        int(logical_flips[i]), "" if bpi is None else int(bpi[i]), "" if osd is None else int(osd[i]), tm])
    first = res.rep == 1
    mean_first = float(res.time_ns[first].mean())
    info.setdefault("shots_requested", n)
    info.setdefault("shots", n)
    run_row = dict(base_row, rounds=rounds, seed=idx["seed"], reps=reps, core=core,
                   num_detectors=idx["num_detectors"], num_errors=idx["num_errors"], num_observables=idx["num_observables"],
                   timing_method=tm, shots_requested=info["shots_requested"], shots=info["shots"],
                   floor_ns=info.get("floor_ns", ""), graph_build_ns=info.get("graph_build_ns", ""),
                   cycles_available=info.get("cycles_available", ""), pilot_median_ns=info.get("pilot_median_ns", ""),
                   batch_size=info.get("batch_size", ""), driver_wall_s=info.get("driver_wall_s", ""),
                   total_wall_s=round(time.time() - t_wall0, 1),
                   mean_ns_first=round(mean_first, 1), mean_per_round_ns_first=round(mean_first / rounds, 1),
                   logical_error_rate=round(float(logical_error[first].mean()), 6),
                   governor=snap0["governor"], boost=snap0["boost"], started=snap0["timestamp"], finished=snap1["timestamp"],
                   raw_file=str(out.relative_to(data.root)))
    append_csv(out.parent / "runs.csv", run_row)
    for phase, s in (("start", snap0), ("end", snap1)):
        append_csv(out.parent / "machine_snapshots.csv", dict(base_row, phase=phase, **s))
    print(f"  wrote {out}  shots={n} mean_ns(first)={mean_first:.0f} per_round={mean_first/rounds:.0f} "
          f"LER={logical_error[first].mean():.2e} floor_ns={info.get('floor_ns')} method={tm}", flush=True)
