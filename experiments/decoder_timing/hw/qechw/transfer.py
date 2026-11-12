"""Relay-BP work-counter transfer on the bivariate-bicycle syndromes.

IBM's Relay-BP (package relay-bp, Rust core) runs with the configuration of the FPGA paper in split X/Z mode
on the syndromes and records per shot the work counters that the FPGA's latency is a deterministic function of:

    iterations_x, iterations_z    BP iterations of the X-error and the Z-error decoder (IBM naming: H_X = Z-type
                                  detector rows), total over relay legs
    iterations_window             max of the two (the decoders run in parallel on hardware)
    legs_x, legs_z                relay legs executed (1 = the first leg converged); -1 = shot without per-leg log
    converged_x, converged_z      1 if a solution was found within the leg budget

Transfer: time_ns = c0 + ns_per_iteration x iterations_window, hard bound = c0 + ns_per_iteration x (T0 + R Tr).
The result is an input-induced execution-time distribution, not a pWCET. Shots are decoded in contiguous chunks;
the decoders of chunk k are seeded with 1000 k + {0, 1} (X, Z), so a rerun reproduces every count.

Output: raw/fpga_transfer_<variant>_<code>_d<d>_p<p>.csv.gz (one row per shot and counter) and, for the logged
subsample, raw/legs/<variant>_<code>_d<d>_p<p>.csv.gz (shot, basis, leg, iterations, converged).
"""
from __future__ import annotations

import csv
import gzip
import os
import shutil
import tempfile
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np
import stim

from .config import Relay, Run, Transfer
from .data import RAW_COLUMNS, DataDir, config_id
from .xz import xz_matrices

COUNTERS = ["iterations_x", "iterations_z", "iterations_window", "legs_x", "legs_z", "converged_x", "converged_z",
            "cpu_wall_ns_x", "cpu_wall_ns_z"]


def parse_leg_log(path: Path) -> list[list[tuple[int, int]]]:
    """relay_logging.out: one line per executed leg, `leg - 1, iterations, converged, best`; the first leg of each
    decode has index -1. Returns per decode the list of (iterations, converged) of its legs."""
    out = []
    cur = None
    with open(path) as f:
        for ln in f:
            if ln.startswith("#") or not ln.strip():   # two header lines: parameters, column names
                continue
            parts = [p.strip() for p in ln.split(",")]
            if len(parts) < 3:
                continue
            idx, it, conv = int(parts[0]), int(parts[1]), int(parts[2])
            if idx == -1:
                cur = []
                out.append(cur)
            cur.append((it, conv))
    return out


def decode_chunk(args):
    """Decode shots lo..hi with both decoders; runs in a worker process."""
    (chunk_id, lo, hi, circuit_path, dets_path, obs_path, num_det, num_obs, relay, variant, log_legs) = args
    import relay_bp
    c = stim.Circuit.from_file(circuit_path)
    M = xz_matrices(c)
    rb = (num_det + 7) // 8
    raw = np.fromfile(dets_path, dtype=np.uint8)
    dets = np.unpackbits(raw[lo * rb: hi * rb].reshape(hi - lo, rb), axis=1, bitorder="little")[:, :num_det].astype(np.uint8)
    ob = (num_obs + 7) // 8
    obs = np.unpackbits(np.fromfile(obs_path, dtype=np.uint8)[lo * ob: hi * ob].reshape(hi - lo, ob), axis=1,
                        bitorder="little")[:, :num_obs].astype(np.uint8)
    cls = getattr(relay_bp, variant.decoder_class)
    n = hi - lo
    res = {}
    workdir = tempfile.mkdtemp(prefix=f"relay_{variant.name}_{chunk_id}_")
    cwd = os.getcwd()
    for bi, k in enumerate(("X", "Z")):
        legdir = Path(workdir) / k
        legdir.mkdir()
        os.chdir(legdir)   # relay-bp writes its leg log into the working directory
        if log_legs:
            (legdir / "relay_logging.out").write_text("")
        dec = cls(M.H[k], M.priors[k].astype(np.float64), seed=1000 * chunk_id + bi, logging=bool(log_legs),
                  **relay.decoder_kwargs(), **variant.extra_kwargs())
        it = np.empty(n, dtype=np.int64); conv = np.empty(n, dtype=np.int8)
        preds = np.zeros((n, num_obs), dtype=np.uint8)
        wall = np.empty(n, dtype=np.int64)
        for i in range(n):
            s = dets[i, M.det_index[k]]
            t0 = time.perf_counter_ns()
            r = dec.decode_detailed(s)
            wall[i] = time.perf_counter_ns() - t0
            it[i] = r.iterations; conv[i] = 1 if r.success else 0
            if k == "X":  # the X-error decoder owns the Z-memory observables
                preds[i] = (M.obs[k] @ np.asarray(r.decoding, dtype=np.int64)) % 2
        os.chdir(cwd)
        legs = parse_leg_log(legdir / "relay_logging.out") if log_legs else None
        res[k] = dict(it=it, conv=conv, preds=preds, wall=wall, legs=legs)
    shutil.rmtree(workdir, ignore_errors=True)
    flips = (res["X"]["preds"] ^ obs).sum(axis=1)
    return chunk_id, lo, hi, res, flips


def transfer(data: DataDir, relay: Relay, settings: Transfer, run: Run, force: bool = False) -> None:
    variant = relay.variants[run.variant]
    name = run.name
    out = data.raw / f"fpga_transfer_{variant.name}_{name}.csv.gz"
    if out.exists() and not force:
        print("exists:", out)
        return
    syn = data.syndromes
    circuit_path = syn / f"{name}.stim"
    c = stim.Circuit.from_file(str(circuit_path))
    num_det, num_obs = c.num_detectors, c.num_observables
    rb = (num_det + 7) // 8
    total = os.path.getsize(syn / f"{name}.dets.b8") // rb
    n = min(run.shots, total) if run.shots else total
    workers = settings.workers or max(1, os.cpu_count() - 2)
    hb = relay.hard_bound_ns
    cid = config_id("fpga", variant.name, run.code, run.d, run.p)
    print(f"[{cid}] shots={n} workers={workers} chunk={settings.chunk} hard_bound_ns={hb:.0f}", flush=True)
    tasks = []
    for k, lo in enumerate(range(0, n, settings.chunk)):
        hi = min(n, lo + settings.chunk)
        tasks.append((k, lo, hi, str(circuit_path), str(syn / f"{name}.dets.b8"), str(syn / f"{name}.obs.b8"),
                      num_det, num_obs, relay, variant, lo < settings.log_legs))
    t0 = time.time()
    results = {}
    with ProcessPoolExecutor(max_workers=workers) as ex:
        for chunk_id, lo, hi, res, flips in ex.map(decode_chunk, tasks):
            results[chunk_id] = (lo, hi, res, flips)
            done = sum(h - l for l, h, _, _ in results.values())
            if chunk_id % 5 == 0:
                print(f"  {done}/{n} shots, {time.time()-t0:.0f} s", flush=True)
    out.parent.mkdir(parents=True, exist_ok=True)
    (data.raw / "legs").mkdir(exist_ok=True)
    legs_out = data.raw / "legs" / f"{variant.name}_{name}.csv.gz"
    with gzip.open(out, "wt", newline="") as f, gzip.open(legs_out, "wt", newline="") as fl:
        w = csv.writer(f); wl = csv.writer(fl)
        w.writerow(RAW_COLUMNS)
        wl.writerow(["config_id", "shot", "basis", "leg", "iterations", "converged"])
        for chunk_id in sorted(results):
            lo, hi, res, flips = results[chunk_id]
            itx, itz = res["X"]["it"], res["Z"]["it"]
            legs_x = np.ones(hi - lo, dtype=int); legs_z = np.ones(hi - lo, dtype=int)
            for k, key in (("X", legs_x), ("Z", legs_z)):
                if res[k]["legs"] is not None:
                    for i, L in enumerate(res[k]["legs"]):
                        key[i] = len(L)
                        for j, (li, lc) in enumerate(L):
                            wl.writerow([cid, lo + i, k, j, li, lc])
                else:
                    key[:] = -1
            for i in range(hi - lo):
                shot = lo + i
                win = max(itx[i], itz[i])
                t_ns = relay.c0_ns + relay.ns_per_iteration * win
                le = int(flips[i] > 0)
                vals = [itx[i], itz[i], win, legs_x[i], legs_z[i], res["X"]["conv"][i], res["Z"]["conv"][i],
                        res["X"]["wall"][i], res["Z"]["wall"][i]]
                for cn, cv in zip(COUNTERS, vals):
                    w.writerow([cid, "fpga", "transfer", variant.name, run.code, run.d, run.p, run.d, shot, 1, cn, int(cv),
                                f"{t_ns:.1f}", f"{hb:.0f}", le, int(flips[i]), "transfer", relay.source])
    itw = np.concatenate([np.maximum(r[2]["X"]["it"], r[2]["Z"]["it"]) for r in results.values()])
    itx = np.concatenate([r[2]["X"]["it"] for r in results.values()])
    itz = np.concatenate([r[2]["Z"]["it"] for r in results.values()])
    fl = np.concatenate([r[3] for r in results.values()])
    t_mean = relay.c0_ns + relay.ns_per_iteration * itw.mean()
    print(f"  wrote {out}: shots={n} iters X mean {itx.mean():.2f} Z mean {itz.mean():.2f} window mean {itw.mean():.2f} "
          f"p99.9 {np.quantile(itw, 0.999):.0f} max {itw.max()} | time_ns mean {t_mean:.0f} per round {t_mean / run.d:.1f} "
          f"| block LER {np.mean(fl > 0):.2e} | {time.time()-t0:.0f} s", flush=True)
