"""The decoders and how each is timed.

NativeDecoder: PyMatching, fusion-blossom and Chromobius run inside their C++/Rust timing drivers
(drivers/), pinned with taskset; the driver times every decode call and writes the shots to a CSV.
LdpcDecoder: BP, BP+OSD and BP+LSD (`ldpc`) run in this process, pinned with sched_setaffinity, timed
with time.perf_counter_ns() around decode().

Both follow the same protocol: call-overhead floor on the all-zero syndrome, untimed warm-up, then
`reps` interleaved timed passes over the shots.
"""
from __future__ import annotations

import os
import subprocess
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import numpy as np

from . import parameters as P
from .grid import GridPoint, max_seconds_per_rep
from .machine import CycleCounter
from .syndromes import load_b8

DRIVERS = Path(__file__).resolve().parents[1] / "drivers"


class Skipped(Exception):
    """The grid point is skipped by the stop rule; the record for skipped.csv is attached."""

    def __init__(self, record: dict):
        super().__init__(record["reason"])
        self.record = record


@dataclass
class Timed:
    """The timed calls of one run: one entry per (pass, shot)."""
    shot: np.ndarray
    rep: np.ndarray
    time_ns: np.ndarray
    cycles: np.ndarray            # -1 where no cycle count is available
    pred: np.ndarray              # predicted observable flips as a bit mask
    bp_iterations: np.ndarray | None = None
    osd_triggered: np.ndarray | None = None


def parse_kv(text: str) -> dict:
    out = {}
    for line in text.splitlines():
        if "=" in line:
            k, v = line.split("=", 1)
            out[k.strip()] = v.strip()
    return out


@dataclass(frozen=True)
class NativeDecoder:
    name: str
    binary: Path
    inputs: Callable[[dict, Path, GridPoint], list[str]]   # driver arguments that name the decoding problem

    def run(self, idx: dict, syndromes: Path, point: GridPoint, reps: int, shots: int, core: int | None,
            info: dict) -> Timed:
        with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as tmp:
            tmp_path = tmp.name
        cmd = [str(self.binary)] + self.inputs(idx, syndromes, point)
        cmd += ["--dets", str(syndromes / idx["dets_file"]), "--out", tmp_path, "--reps", str(reps),
                "--warmup", str(P.WARMUP_SHOTS), "--floor", str(P.FLOOR_CALLS)]
        if shots:
            cmd += ["--max_shots", str(shots)]
        if core is not None:
            cmd = ["taskset", "-c", str(core)] + cmd
        env = dict(os.environ, OMP_NUM_THREADS="1", RAYON_NUM_THREADS="1")
        t0 = time.time()
        res = subprocess.run(cmd, capture_output=True, text=True, env=env)
        if res.returncode != 0:
            raise SystemExit(f"driver failed ({res.returncode}):\n{res.stderr}")
        kv = parse_kv(res.stdout)
        info.update(driver_wall_s=round(time.time() - t0, 1), floor_ns=int(kv.get("floor_ns", -1)),
                    graph_build_ns=int(kv.get("graph_build_ns", -1)),
                    cycles_available=int(kv.get("cycles_available", 0)), timing_method="native")
        import pandas as pd
        data = pd.read_csv(tmp_path, dtype={"shot": np.int64, "rep": np.int64, "time_ns": np.int64,
                                            "cycles": "float64", "pred": np.int64})
        os.unlink(tmp_path)
        cycles = data["cycles"].fillna(-1).astype(np.int64).to_numpy()
        return Timed(shot=data["shot"].to_numpy(), rep=data["rep"].to_numpy(), time_ns=data["time_ns"].to_numpy(),
                     cycles=cycles, pred=data["pred"].to_numpy())


def obs_mask_of(obs_mat, corr) -> int:
    """Predicted observable flips as a bit mask (bit k = observable k), like the native drivers."""
    v = (obs_mat @ corr) % 2
    return int(sum(int(b) << k for k, b in enumerate(np.asarray(v).ravel())))


@dataclass(frozen=True)
class LdpcDecoder:
    name: str
    build: Callable[[object, np.ndarray], object]   # (check matrix, priors) -> ldpc decoder

    def run(self, idx: dict, syndromes: Path, point: GridPoint, reps: int, shots: int, core: int | None,
            info: dict) -> Timed:
        import stim
        from stimbposd.dem_to_matrices import detector_error_model_to_check_matrices

        if core is not None:
            os.sched_setaffinity(0, {core})
        os.environ["OMP_NUM_THREADS"] = "1"
        dem = stim.DetectorErrorModel.from_file(syndromes / idx["dem_file"])
        mats = detector_error_model_to_check_matrices(dem, allow_undecomposed_hyperedges=True)
        H = mats.check_matrix.tocsr()
        obs_mat = mats.observables_matrix.tocsr()
        priors = np.asarray(mats.priors, dtype=float)
        t_build0 = time.perf_counter_ns()
        dec = self.build(H, priors)
        info["graph_build_ns"] = time.perf_counter_ns() - t_build0
        num_det = int(idx["num_detectors"])
        dets = load_b8(syndromes / idx["dets_file"], num_det, shots or None).astype(np.uint8)
        n = dets.shape[0]
        cyc = CycleCounter()
        info["cycles_available"] = int(cyc.available)
        perf = time.perf_counter_ns

        # call-overhead floor on the all-zero syndrome
        zero = np.zeros(num_det, dtype=np.uint8)
        ft = np.empty(P.FLOOR_CALLS, dtype=np.int64)
        for i in range(P.FLOOR_CALLS):
            t0 = perf(); dec.decode(zero); ft[i] = perf() - t0
        floor = int(np.median(ft))
        info["floor_ns"] = floor

        # pilot: decide batch timing (plain BP only) and the time budget
        npilot = min(200, n)
        pt = np.empty(npilot, dtype=np.int64)
        for i in range(npilot):
            t0 = perf(); dec.decode(dets[n - 1 - i]); pt[i] = perf() - t0
        pilot_med = float(np.median(pt))
        batch = self.name == "bp" and pilot_med < P.BATCH_IF_BELOW_X_FLOOR * floor
        if self.name == "bposd" and pt.mean() > P.SKIP_BPOSD_ABOVE_NS:
            # the message text matches the records of the campaign in skipped.csv
            msg = (f"BP+OSD {point.code} d={point.d} p={point.p}: pilot mean {pt.mean()*1e-9:.2f} s/shot > 1 s "
                   "-> skipped (sec. 4.3)")
            raise Skipped(dict(decoder=self.name, code=point.code, d=point.d, p=point.p, pilot_mean_ns=int(pt.mean()),
                               pilot_median_ns=int(pilot_med), reason=msg))
        est = float(pt.mean()) * n * 1e-9
        budget = max_seconds_per_rep(self.name, point.code)
        shots_used = n
        if est > budget:
            shots_used = max(P.MIN_SHOTS, int(n * budget / est))
            print(f"  time budget: pilot mean {pt.mean()*1e-6:.2f} ms/shot -> reduce shots {n} -> {shots_used}", flush=True)
        info.update(pilot_median_ns=int(pilot_med), shots_requested=n, shots=shots_used,
                    timing_method="batch" if batch else "python", batch_size=P.BATCH_SIZE if batch else "")
        n = shots_used

        # untimed warm-up
        for i in range(min(P.WARMUP_SHOTS, n)):
            dec.decode(dets[i])

        # timed, interleaved passes
        time_ns = np.empty(reps * n, dtype=np.int64)
        cycles = np.full(reps * n, -1, dtype=np.int64)
        iters = np.empty(reps * n, dtype=np.int64)
        osd = np.zeros(reps * n, dtype=np.int64)
        preds = np.empty(reps * n, dtype=np.int64)
        has_conv = hasattr(dec, "converge")
        t_start = time.time()
        for rep in range(reps):
            base = rep * n
            if batch:
                for b0 in range(0, n, P.BATCH_SIZE):
                    b1 = min(n, b0 + P.BATCH_SIZE)
                    c0 = cyc.read()
                    t0 = perf()
                    for i in range(b0, b1):
                        corr = dec.decode(dets[i])
                        iters[base + i] = dec.iter
                        preds[base + i] = obs_mask_of(obs_mat, corr)
                    t1 = perf()
                    c1 = cyc.read()
                    time_ns[base + b0:base + b1] = (t1 - t0) // (b1 - b0)
                    if c0 >= 0 and c1 >= 0:
                        cycles[base + b0:base + b1] = (c1 - c0) // (b1 - b0)
            else:
                for i in range(n):
                    s = dets[i]
                    c0 = cyc.read()
                    t0 = perf()
                    corr = dec.decode(s)
                    t1 = perf()
                    c1 = cyc.read()
                    time_ns[base + i] = t1 - t0
                    if c0 >= 0 and c1 >= 0:
                        cycles[base + i] = c1 - c0
                    iters[base + i] = dec.iter
                    if has_conv:
                        osd[base + i] = 0 if dec.converge else 1
                    preds[base + i] = obs_mask_of(obs_mat, corr)
            print(f"  rep {rep+1}/{reps} done, {time.time()-t_start:.0f} s elapsed", flush=True)
        info["driver_wall_s"] = round(time.time() - t_start, 1)
        cyc.close()
        if self.name == "bp":
            osd[:] = 0
        return Timed(shot=np.tile(np.arange(n), reps), rep=np.repeat(np.arange(1, reps + 1), n), time_ns=time_ns,
                     cycles=cycles, pred=preds, bp_iterations=iters, osd_triggered=osd)


def _bp(H, priors):
    from ldpc.bp_decoder import BpDecoder
    return BpDecoder(H, error_channel=list(priors), max_iter=P.BP_MAX_ITER, bp_method=P.BP_METHOD,
                     omp_thread_count=1, input_vector_type="syndrome")


def _bposd(H, priors):
    from ldpc.bposd_decoder import BpOsdDecoder
    return BpOsdDecoder(H, error_channel=list(priors), max_iter=P.BP_MAX_ITER, bp_method=P.BP_METHOD,
                        omp_thread_count=1, input_vector_type="syndrome", osd_method=P.OSD_METHOD, osd_order=P.OSD_ORDER)


def _bplsd(H, priors):
    from ldpc.bplsd_decoder import BpLsdDecoder
    return BpLsdDecoder(H, error_channel=list(priors), max_iter=P.BP_MAX_ITER, bp_method=P.BP_METHOD,
                        omp_thread_count=1, input_vector_type="syndrome", lsd_method=P.LSD_METHOD, lsd_order=P.LSD_ORDER)


DECODERS: dict[str, NativeDecoder | LdpcDecoder] = {
    "pymatching": NativeDecoder(
        "pymatching", DRIVERS / "pymatching" / "build" / "pm_timing",
        lambda idx, syn, pt: ["--dem", str(syn / (idx.get("decomposed_dem_file") or idx["dem_file"]))]),
    "fusionblossom": NativeDecoder(
        "fusionblossom", DRIVERS / "fusionblossom" / "target" / "release" / "fb_timing",
        lambda idx, syn, pt: ["--graph", str(syn / f"{pt.name}.fbgraph.json")]),
    "chromobius": NativeDecoder(
        "chromobius", DRIVERS / "chromobius" / "build" / "cb_timing",
        lambda idx, syn, pt: ["--dem", str(syn / idx["dem_file"])]),
    "bp": LdpcDecoder("bp", _bp),
    "bposd": LdpcDecoder("bposd", _bposd),
    "bplsd": LdpcDecoder("bplsd", _bplsd),
}
