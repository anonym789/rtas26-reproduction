"""GPU measurement of Relay-BP (NVIDIA CUDA-Q QEC nv-qldpc-decoder) on the bivariate-bicycle syndromes.

One algorithm on three platforms: the decoder is configured like IBM's FPGA paper in split X/Z mode on the same
matrices as the transfer. GPU mapping: pre_iter = T0, max_iterations = Tr (per leg), num_sets = R, stopping
criterion FirstConv (S = 1) or NConv (S > 1); proc_float fp32; bp_seed fixed per decoder.

Timing: syndromes pre-converted to Python lists, warm-up calls, interleaved passes, time.perf_counter_ns around
each single-shot decode() (end to end on the host, timing_method = host_monotonic). The decoder binary is closed,
so CUDA events cannot be placed inside it; a separate pass over cupti_shots shots records every kernel and memcpy
with CUPTI and attributes them to the decode call by timestamps (timing_method = cupti_kernel): kernel_ns = sum of
kernel durations, gpu_span_ns = first kernel start to last kernel/memcpy end, host_ns = host wall. Batched
throughput: decode_batch on the first batch_shots shots for each batch size (separate decoders), per shot.

Per window the X-error and Z-error decoders run one after the other on one GPU: time_ns = host_ns_x + host_ns_z
(the FPGA transfer uses max(x, z) because its two decoders are parallel hardware; both are kept as counters).

Outputs: raw/gpu_measured_<variant>_<code>_d<d>_p<p>.csv.gz, raw/gpu_cupti_<...>.csv.gz, raw/gpu_batch_<...>.csv
and raw/gpu_runs.csv (environment per run).
"""
from __future__ import annotations

import csv
import gzip
import subprocess
import time
from pathlib import Path

import numpy as np
import stim

from .config import Gpu, Relay, Run
from .data import RAW_COLUMNS, DataDir, config_id
from .xz import xz_matrices

COUNTERS = ["iterations_x", "iterations_z", "iterations_window", "converged_x", "converged_z", "host_ns_x", "host_ns_z"]


def nvsmi(query: str) -> str:
    try:
        return subprocess.run(["nvidia-smi", f"--query-gpu={query}", "--format=csv,noheader"], capture_output=True,
                              text=True, timeout=20).stdout.strip()
    except Exception as e:
        return f"n/a ({e})"


def build_decoder(qec, relay: Relay, variant: dict, H, priors, device: int, seed: int, batch: int = 1):
    srelay = {"pre_iter": relay.pre_iter, "num_sets": relay.num_sets, "stopping_criterion": variant["stopping_criterion"]}
    if "stop_nconv" in variant:
        srelay["stop_nconv"] = variant["stop_nconv"]
    return qec.get_decoder("nv-qldpc-decoder", H, error_rate_vec=priors, use_sparsity=True, bp_method=3, composition=1,
                           max_iterations=relay.set_max_iter, gamma0=relay.gamma0, gamma_dist=list(relay.gamma_interval),
                           proc_float="fp32", cuda_device_id=device, srelay_config=srelay,
                           opt_results={"num_iter": True}, bp_seed=seed, bp_batch_size=batch)


class CuptiTrace:
    """Collect kernel/memcpy activity records (start, end in CUPTI ns)."""

    def __init__(self):
        from cupti import cupti
        self.cupti = cupti
        self.records = []

        def requested():
            return 8 * 1024 * 1024, 0

        def completed(activities):
            for a in activities:
                k = a.kind
                if k in (cupti.ActivityKind.CONCURRENT_KERNEL, cupti.ActivityKind.KERNEL):
                    self.records.append(("k", a.start, a.end))
                elif k in (cupti.ActivityKind.MEMCPY, cupti.ActivityKind.MEMSET):
                    self.records.append(("m", a.start, a.end))
        cupti.activity_register_callbacks(requested, completed)
        for kind in (cupti.ActivityKind.CONCURRENT_KERNEL, cupti.ActivityKind.MEMCPY, cupti.ActivityKind.MEMSET):
            cupti.activity_enable(kind)

    def now(self) -> int:
        return self.cupti.get_timestamp()

    def flush(self):
        self.cupti.activity_flush_all(1)

    def disable(self):
        """Stop tracing (otherwise every later kernel launch pays the CUPTI/callback overhead)."""
        c = self.cupti
        for kind in (c.ActivityKind.CONCURRENT_KERNEL, c.ActivityKind.MEMCPY, c.ActivityKind.MEMSET):
            try:
                c.activity_disable(kind)
            except Exception:
                pass
        self.flush()

    def attribute(self, windows):
        """windows: list of (t0, t1) host timestamps -> per window (kernel_ns, memcpy_ns, span_ns, n_kernels)."""
        recs = sorted(self.records, key=lambda r: r[1])
        starts = np.array([r[1] for r in recs]); ends = np.array([r[2] for r in recs]); kinds = np.array([r[0] for r in recs])
        out = []
        for t0, t1 in windows:
            sel = (starts >= t0) & (ends <= t1)
            if not sel.any():
                out.append((0, 0, 0, 0)); continue
            k = sel & (kinds == "k"); m = sel & (kinds == "m")
            out.append((int((ends[k] - starts[k]).sum()), int((ends[m] - starts[m]).sum()),
                        int(ends[sel].max() - starts[sel].min()), int(k.sum())))
        return out


def measure(data: DataDir, relay: Relay, settings: Gpu, run: Run, fallback_syndromes: Path | None = None,
            force: bool = False, qec=None) -> None:
    """Measure one run; grid points missing from the experiment's syndromes are read from fallback_syndromes (the
    CPU experiment's). qec is the CUDA-Q QEC module (imported here unless given)."""
    if qec is None:
        import cudaq_qec as qec
    variant = settings.variants[run.variant]
    name = run.name
    out = data.raw / f"gpu_measured_{run.variant}_{name}.csv.gz"
    if out.exists() and not force:
        print("exists:", out)
        return
    syn = data.syndromes
    if not (syn / f"{name}.stim").exists() and fallback_syndromes is not None:
        syn = fallback_syndromes
    c = stim.Circuit.from_file(str(syn / f"{name}.stim"))
    M = xz_matrices(c)
    nd, no = c.num_detectors, c.num_observables
    rb = (nd + 7) // 8
    raw = np.fromfile(syn / f"{name}.dets.b8", dtype=np.uint8)
    total = raw.size // rb
    n = min(run.shots, total) if run.shots else total
    dets = np.unpackbits(raw[: n * rb].reshape(n, rb), axis=1, bitorder="little")[:, :nd].astype(np.uint8)
    ob = (no + 7) // 8
    obs = np.unpackbits(np.fromfile(syn / f"{name}.obs.b8", dtype=np.uint8)[: n * ob].reshape(n, ob), axis=1,
                        bitorder="little")[:, :no].astype(np.uint8)
    cid = config_id("gpu", run.variant, run.code, run.d, run.p)
    dev, reps = settings.device, settings.reps
    gpu_name = nvsmi("name").splitlines()[dev] if nvsmi("name") else "n/a"
    print(f"[{cid}] shots={n} reps={reps} device={dev} ({gpu_name}) clocks sm={nvsmi('clocks.sm').splitlines()[dev]}", flush=True)

    # pre-converted inputs (host conversion outside the timed window)
    syn_lists = {k: [dets[i, M.det_index[k]].tolist() for i in range(n)] for k in ("X", "Z")}
    H = {k: M.H[k].tocsr().astype(np.uint8) for k in ("X", "Z")}
    pri = {k: M.priors[k].astype(np.float64) for k in ("X", "Z")}
    decs = {k: build_decoder(qec, relay, variant, H[k], pri[k], dev, seed=bi) for bi, k in enumerate(("X", "Z"))}
    obsmat = M.obs["X"].tocsr()

    # single-shot host-timed passes
    host = {k: np.empty((reps, n), dtype=np.int64) for k in ("X", "Z")}
    iters = {k: np.empty((reps, n), dtype=np.int64) for k in ("X", "Z")}
    conv = {k: np.empty((reps, n), dtype=np.int8) for k in ("X", "Z")}
    flips = np.zeros((reps, n), dtype=np.int64)
    t_start = time.time()
    for k in ("X", "Z"):
        for i in range(min(settings.warmup, n)):
            decs[k].decode(syn_lists[k][i])
    for rep in range(reps):
        for k in ("X", "Z"):
            dec, S = decs[k], syn_lists[k]
            for i in range(n):
                t0 = time.perf_counter_ns(); r = dec.decode(S[i]); t1 = time.perf_counter_ns()
                host[k][rep, i] = t1 - t0
                iters[k][rep, i] = r.opt_results["num_iter"] if r.opt_results else -1
                conv[k][rep, i] = 1 if r.converged else 0
                if k == "X":
                    e = np.asarray(r.result, dtype=np.int64)
                    flips[rep, i] = int((((obsmat @ e) % 2) ^ obs[i]).sum())
        print(f"  pass {rep+1}/{reps}: host mean X {host['X'][rep].mean()/1e3:.1f} us, Z {host['Z'][rep].mean()/1e3:.1f} us; {time.time()-t_start:.0f} s", flush=True)

    out.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(out, "wt", newline="") as f:
        w = csv.writer(f)
        w.writerow(RAW_COLUMNS)
        for rep in range(reps):
            for i in range(n):
                t_ns = int(host["X"][rep, i] + host["Z"][rep, i])
                vals = [iters["X"][rep, i], iters["Z"][rep, i], max(iters["X"][rep, i], iters["Z"][rep, i]), conv["X"][rep, i], conv["Z"][rep, i],
                        host["X"][rep, i], host["Z"][rep, i]]
                for cn, cv in zip(COUNTERS, vals):
                    w.writerow([cid, "gpu", "measured", run.variant, run.code, run.d, run.p, run.d, i, rep + 1, cn, int(cv), t_ns, "",
                                int(flips[rep, i] > 0), int(flips[rep, i]), "host_monotonic", settings.source])
    print(f"  wrote {out}", flush=True)

    # batched throughput
    bout = data.raw / f"gpu_batch_{run.variant}_{name}.csv"
    nb = min(settings.batch_shots, n)
    with open(bout, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["config_id", "decoder_basis", "batch_size", "rep", "shots", "wall_ns", "ns_per_shot", "converged_fraction"])
        for bs in settings.batch_sizes:
            for bi, k in enumerate(("X", "Z")):
                dec = build_decoder(qec, relay, variant, H[k], pri[k], dev, seed=bi, batch=bs)
                S = syn_lists[k][:nb]
                dec.decode_batch(S[:bs])  # warm-up
                for rep in range(3):
                    t0 = time.perf_counter_ns(); convs = []
                    for lo in range(0, nb, bs):
                        r = dec.decode_batch(S[lo:lo + bs]); convs.append(np.mean(r.converged))
                    wall = time.perf_counter_ns() - t0
                    w.writerow([cid, k, bs, rep + 1, nb, wall, wall / nb, float(np.mean(convs))])
                print(f"  batch {bs} {k}: {wall/nb/1e3:.1f} us/shot", flush=True)
                del dec

    # CUPTI kernel-timing pass on a subsample
    nc = min(settings.cupti_shots, n)
    cup_out = data.raw / f"gpu_cupti_{run.variant}_{name}.csv.gz"
    try:
        tr = CuptiTrace()
        res = {}
        for k in ("X", "Z"):
            dec, S = decs[k], syn_lists[k]
            for i in range(200):
                dec.decode(S[i])
            windows = []; hostw = []
            for i in range(nc):
                t0 = tr.now(); h0 = time.perf_counter_ns(); dec.decode(S[i]); h1 = time.perf_counter_ns(); t1 = tr.now()
                windows.append((t0, t1)); hostw.append(h1 - h0)
            tr.flush()
            res[k] = (tr.attribute(windows), hostw)
            tr.records.clear()
        with gzip.open(cup_out, "wt", newline="") as f:
            w = csv.writer(f)
            w.writerow(RAW_COLUMNS)
            for i in range(nc):
                kx, mx, sx_, nx = res["X"][0][i]; kz, mz, sz, nz = res["Z"][0][i]
                t_ns = kx + kz
                vals = {"kernel_ns_x": kx, "kernel_ns_z": kz, "memcpy_ns_x": mx, "memcpy_ns_z": mz, "gpu_span_ns_x": sx_, "gpu_span_ns_z": sz,
                        "n_kernels_x": nx, "n_kernels_z": nz, "host_ns_x": res["X"][1][i], "host_ns_z": res["Z"][1][i]}
                for cn, cv in vals.items():
                    w.writerow([cid, "gpu", "measured", run.variant, run.code, run.d, run.p, run.d, i, 1, cn, int(cv), t_ns, "", "", "",
                                "cupti_kernel", settings.source])
        tr.disable()
        kx = np.array([r[0] for r in res["X"][0]]); hx = np.array(res["X"][1])
        print(f"  CUPTI ({nc} shots): X kernel-only mean {kx.mean()/1e3:.1f} us vs host {hx.mean()/1e3:.1f} us; wrote {cup_out}", flush=True)
    except Exception as e:
        print(f"  CUPTI pass failed: {e!r}", flush=True)

    runs = data.raw / "gpu_runs.csv"
    row = dict(config_id=cid, device=dev, gpu=gpu_name, driver=nvsmi("driver_version").splitlines()[dev],
               sm_mhz=nvsmi("clocks.sm").splitlines()[dev], mem_mhz=nvsmi("clocks.mem").splitlines()[dev],
               shots=n, reps=reps, warmup=settings.warmup, cupti_shots=nc,
               started=time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(t_start)),
               finished=time.strftime("%Y-%m-%dT%H:%M:%S"), version=decs["X"].get_version(),
               loadavg=open("/proc/loadavg").read().split()[0])
    new = not runs.exists()
    with open(runs, "a", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(row))
        if new:
            w.writeheader()
        w.writerow(row)
