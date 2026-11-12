"""Board correction of the cycle-accurate Micro Blossom simulation: fit, validation and transfer.

The CPU cost a + b r per loop iteration (board.py) is fitted at d = 9 (f = 93 MHz) to the board's latency histogram
of the *same* 100,014 syndromes (artifact tmp-tty/d_9_p_1.0000e-03_N_100000.txt), by minimising the L1 distance of
log-latency quantiles q = 0.01..0.9999. For d = 13 (f = 62 MHz, Table 4 of arXiv 2502.14787) a and b are scaled by
the bus read-latency ratio read(62 MHz) / read(93 MHz) and compared with the d = 13 board histogram without refitting
(validation). The corrected simulation of the CPU experiment's syndromes is written as an input-induced execution-time
distribution (method = simulated, calibration = board histogram).

The artifact's files are in the literature folder (micro_blossom/): stream mode (round-wise fusion) uses the
histograms in board/, batch mode (block at once) those in board_batch/ (circuit_level_batch/tmp-tty of the artifact,
same syndromes as the batch simulation). The batch tables also evaluate the stream-mode a, b; `batch_timeline` in
config.toml selects which set the batch rows use. Also compared: the artifact's batch means
(circuit_level_batch/d_<d>.txt). Where the stream run of the artifact's stream-folder syndromes ("board") exists in
both modes, it gives the per-shot comparison of batch and stream on identical syndromes.

Outputs: stats/level2_{validation,ccdf,correction}.csv (stream), stats/level2_batch_{validation,ccdf,checks,
correction}.csv (batch), raw/fpga_sim_microblossomsim_* (stream, where its simulation exists) and
raw/fpga_sim_microblossombatch_surface_d<d>_p0.001.csv.gz (batch; S1 of the paper).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from ..config import MicroBlossom
from ..data import DataDir
from .board import QS, REPORT_Q, Timeline, board_hist, ccdf_rows, corrected, fit, hist_quantiles, ks_tolerant, ks_vs_board, summary

SOURCE_BATCH = ("simulated; Micro Blossom RTL (commit 468af5d, batch mode: block at once, offloading, 4-bit weights) in Verilator 5.014 "
                "driven by the board program; CPU-side replay a + b*resolutions fitted at d = 9 to the artifact's batch board histogram of the "
                "same syndromes, transferred to d = 13 by the bus read-latency ratio and validated there (arXiv 2502.14787 artifact, "
                "zenodo 10.5281/zenodo.14773458)")
SOURCE = ("simulated; Micro Blossom RTL (commit 468af5d, round-wise fusion, offloading, 4-bit weights) in Verilator 5.014 "
          "driven by the board program; board timeline replay with per-iteration CPU cost a + b*resolutions fitted to the VMK180 histogram at d = 9 "
          "(arXiv 2502.14787 artifact, zenodo 10.5281/zenodo.14773458)")


def _board(mb: MicroBlossom) -> dict[int, tuple[float, str]]:
    """d -> (accelerator clock in Hz, board histogram file)."""
    return {d: (mb.freq_hz[d], mb.board_histogram[d]) for d in mb.freq_hz}


def calibrate(data: DataDir, mb: MicroBlossom) -> None:
    data.stats.mkdir(parents=True, exist_ok=True)
    data.raw.mkdir(parents=True, exist_ok=True)
    batch(data, mb, stream_fit(data, mb))


def stream_fit(data: DataDir, mb: MicroBlossom) -> dict:
    """Stream mode: a, b fitted at d = 9 to the board histogram, scaled to d = 13; validation tables and, where the
    stream simulation of the CPU experiment's syndromes exists, its corrected rows. Returns {d: (a, b)}."""
    L2, ART, BOARD = data.level2, data.micro_blossom_artifact, _board(mb)
    rows, cc = [], []
    sims = {d: pd.read_csv(L2 / f"sim_board_d{d}_p0.001.csv.gz") for d in BOARD if (L2 / f"sim_board_d{d}_p0.001.csv.gz").exists()}
    if 9 not in sims:
        raise SystemExit("need the d = 9 board-syndrome simulation")
    f9 = BOARD[9][0]
    lat9, cnt9 = board_hist(ART / "board" / BOARD[9][1])
    bq9, bmean9 = hist_quantiles(lat9, cnt9, QS)
    tls = {d: Timeline(s, mb.layers_board[d]) for d, s in sims.items()}
    err, a9, b9 = fit(sims[9], f9, bq9, tls[9])
    print(f"fit d=9: a = {a9:.0f} ns, b = {b9:.0f} ns per post-final resolution (log-quantile L1 {err:.3f}); shots {len(sims[9])}")
    params = {9: (a9, b9)}
    r = mb.read_latency_ns(BOARD[13][0] / 1e6) / mb.read_latency_ns(BOARD[9][0] / 1e6)
    params[13] = (a9 * r, b9 * r)
    for d, sim in sims.items():
        f = BOARD[d][0]
        lat, cnt = board_hist(ART / "board" / BOARD[d][1])
        bq, bmean = hist_quantiles(lat, cnt, np.array(list(REPORT_Q.values())))
        a, b = params[d]
        cc += ccdf_rows(d, "board measurement (artifact syndromes)", lat=lat, cnt=cnt)
        for label, x in (("simulated, uncorrected", corrected(sim, f, 0, 0)), ("simulated, board-corrected", corrected(sim, f, a, b, tls[d]))):
            cc += ccdf_rows(d, label + " (artifact syndromes)", x=x)
            s = summary(x)
            s["ks_vs_board"] = ks_vs_board(x, lat, cnt)
            s["ks3pct_vs_board"] = ks_tolerant(x, lat, cnt)
            s["frac_above_450ns"] = float((x > 450).mean())
            rows.append(dict(d=d, freq_mhz=f / 1e6, syndromes="artifact (board shots)", series=label, shots=len(x),
                             a_ns=a if "corrected" in label and "un" not in label else 0, b_ns=b if "corrected" in label and "un" not in label else 0,
                             role="fit" if d == 9 else "validation (a, b scaled from d = 9)", **s))
        rows.append(dict(d=d, freq_mhz=f / 1e6, syndromes="artifact (board shots)", series="board measurement (VMK180)", shots=int(cnt.sum()),
                         a_ns=np.nan, b_ns=np.nan, role="reference", mean_ns=bmean,
                         **{f"{k}_ns": v for k, v in zip(REPORT_Q, bq)}, max_ns=float(lat.max()), ks_vs_board=0.0, ks3pct_vs_board=0.0,
                         frac_above_450ns=float(cnt[lat > 450].sum() / cnt.sum())))
    val = pd.DataFrame(rows)
    val.to_csv(data.stats / "level2_validation.csv", index=False, float_format="%.6g")
    print(val[["d", "series", "shots", "mean_ns", "p50_ns", "p90_ns", "p99_ns", "p999_ns", "max_ns", "ks_vs_board", "ks3pct_vs_board", "frac_above_450ns"]].to_string(
        index=False, formatters={"ks_vs_board": "{:.4f}".format, "ks3pct_vs_board": "{:.4f}".format, "frac_above_450ns": "{:.4f}".format}, float_format=lambda v: f"{v:.0f}"))
    # ---- our syndromes: corrected simulation as sec. 8 rows
    for d in (9, 13):
        fs = L2 / f"sim_ours_d{d}_p0.001.csv.gz"
        if not fs.exists():
            continue
        sim = pd.read_csv(fs)
        f = BOARD[d][0]
        a, b = params[d]
        t = corrected(sim, f, a, b, Timeline(sim, mb.layers_ours[d]))
        cc += ccdf_rows(d, "simulated, board-corrected (E2 syndromes)", x=t)
        cid = f"fpga/microblossomsim/surface/d{d}/p0.001"
        frames = []
        for cn in ("cycles", "post_find", "post_resolve", "total_find", "total_resolve", "instructions"):
            frames.append(pd.DataFrame({"config_id": cid, "platform": "fpga", "method": "simulated", "decoder": "microblossomsim",
                                        "code": "surface", "d": d, "p": 0.001, "rounds": d, "shot": sim.shot, "rep": 1,
                                        "counter_name": cn, "counter_value": sim[cn].astype(np.int64), "time_ns": np.round(t, 1),
                                        "hard_bound_ns": "", "logical_error": "", "logical_flips": "",
                                        "timing_method": "simulated_board_corrected", "source": SOURCE}))
        out = data.raw / f"fpga_sim_microblossomsim_surface_d{d}_p0.001.csv.gz"
        pd.concat(frames, ignore_index=True).sort_values("shot", kind="stable").to_csv(out, index=False, compression="gzip")
        s = summary(t)
        print(f"{cid}: {len(t)} shots, mean {s['mean_ns']:.0f} ns, p99 {s['p99_ns']:.0f}, p99.9 {s['p999_ns']:.0f}, max {s['max_ns']:.0f}")
    pd.DataFrame(cc).to_csv(data.stats / "level2_ccdf.csv", index=False, float_format="%.6g")
    corr = [dict(d=d, a_ns=params[d][0], b_ns=params[d][1], freq_mhz=BOARD[d][0] / 1e6,
                 origin="fit to board histogram" if d == 9 else f"d = 9 values x read-latency ratio {r:.3f}", used=True)
            for d in params]
    if 13 in sims:   # diagnostic only: what would a refit at d = 13 give? (not used for any result)
        lat13, cnt13 = board_hist(ART / "board" / BOARD[13][1])
        bq13, _ = hist_quantiles(lat13, cnt13, QS)
        e13, a13, b13 = fit(sims[13], BOARD[13][0], bq13, tls[13])
        corr.append(dict(d=13, a_ns=a13, b_ns=b13, freq_mhz=BOARD[13][0] / 1e6, origin="diagnostic refit at d = 13 (not used)", used=False))
        print(f"diagnostic refit d=13 (not used): a = {a13:.0f} ns, b = {b13:.0f} ns")
    pd.DataFrame(corr).to_csv(data.stats / "level2_correction.csv", index=False, float_format="%.6g")
    return params


def artifact_batch_mean(data: DataDir, d: int, p: float = 1e-3) -> tuple[float, int]:
    """Published batch-mode board mean (circuit_level_batch/d_<d>.txt: p, average latency in s, samples)."""
    rows = np.loadtxt(data.micro_blossom_artifact / "circuit_level_batch" / f"d_{d}.txt", comments="#")
    k = np.flatnonzero(np.isclose(rows[:, 0], p))[0]
    return float(rows[k, 1] * 1e9), int(rows[k, 2])


def single_pass(sim: pd.DataFrame, layers: int) -> pd.Series:
    """Batch records: exactly one loop pass, entered with all layers loaded."""
    one = sim.iterations.astype(str).str.split().str.len() == 1
    lay = sim.iterations.astype(str).str.split(":").str[0] == str(layers)
    return one & lay & (sim.post_find == sim.total_find) & (sim.post_resolve == sim.total_resolve)


def batch(data: DataDir, mb: MicroBlossom, params: dict) -> None:
    """Batch mode: a, b fitted at d = 9 to the batch histogram of the same syndromes, scaled to d = 13 and validated
    there; the stream-mode a, b are evaluated next to them. Writes the batch tables and the corrected rows of the CPU
    experiment's syndromes (raw/fpga_sim_microblossombatch_surface_d<d>_p0.001.csv.gz)."""
    L2, ART, BOARD, BATCH_TIMELINE = data.level2, data.micro_blossom_artifact, _board(mb), mb.batch_timeline
    files = {(src, d): L2 / f"sim_{src}_d{d}_p0.001_batch.csv.gz" for src in ("boardbatch", "board", "ours") for d in (9, 13)}
    if not any(f.exists() for f in files.values()):
        return
    rows, cc, chk = [], [], []
    def check(name, d, source, statistic, value):
        chk.append(dict(check=name, d=d, source=source, statistic=statistic, value=value))
    # ---- batch-mode CPU timeline: fit at d = 9 to the batch histogram of the same syndromes, scale to d = 13
    r = mb.read_latency_ns(BOARD[13][0] / 1e6) / mb.read_latency_ns(BOARD[9][0] / 1e6)
    pb, corr = {}, []
    if files[("boardbatch", 9)].exists() and (ART / "board_batch" / BOARD[9][1]).exists():
        s9 = pd.read_csv(files[("boardbatch", 9)], keep_default_na=False)
        lat9, cnt9 = board_hist(ART / "board_batch" / BOARD[9][1])
        bq9, _ = hist_quantiles(lat9, cnt9, QS)
        err, a9, b9 = fit(s9, BOARD[9][0], bq9, Timeline(s9, mb.layers_board[9]))
        print(f"batch fit d=9: a = {a9:.0f} ns, b = {b9:.0f} ns per resolution (log-quantile L1 {err:.3f}); stream fit: a = {params[9][0]:.0f}, b = {params[9][1]:.0f}")
        pb = {9: (a9, b9), 13: (a9 * r, b9 * r)}
        corr += [dict(d=9, a_ns=a9, b_ns=b9, freq_mhz=int(BOARD[9][0] / 1e6), origin="fit to the batch board histogram (same syndromes)", log_quantile_l1=err, used=BATCH_TIMELINE == "batch fit"),
                 dict(d=13, a_ns=a9 * r, b_ns=b9 * r, freq_mhz=int(BOARD[13][0] / 1e6), origin=f"d = 9 batch values x read-latency ratio {r:.3f}", log_quantile_l1=np.nan, used=BATCH_TIMELINE == "batch fit")]
        if files[("boardbatch", 13)].exists() and (ART / "board_batch" / BOARD[13][1]).exists():
            s13 = pd.read_csv(files[("boardbatch", 13)], keep_default_na=False)
            lat13, cnt13 = board_hist(ART / "board_batch" / BOARD[13][1])
            bq13, _ = hist_quantiles(lat13, cnt13, QS)
            e13, a13, b13 = fit(s13, BOARD[13][0], bq13, Timeline(s13, mb.layers_board[13]))
            corr.append(dict(d=13, a_ns=a13, b_ns=b13, freq_mhz=int(BOARD[13][0] / 1e6), origin="diagnostic refit to the batch histogram at d = 13 (not used)", log_quantile_l1=e13, used=False))
    for d in params:
        corr.append(dict(d=d, a_ns=params[d][0], b_ns=params[d][1], freq_mhz=BOARD[d][0] / 1e6, origin="stream-mode values (E4.md 14.2 step 4)",
                         log_quantile_l1=np.nan, used=BATCH_TIMELINE != "batch fit" or not pb))
    pd.DataFrame(corr).to_csv(data.stats / "level2_batch_correction.csv", index=False, float_format="%.6g")
    use = pb if (BATCH_TIMELINE == "batch fit" and pb) else params
    sets = [("stream-mode a, b", params)] + ([("batch fit", pb)] if pb else [])
    for d in (9, 13):
        f = BOARD[d][0]
        mean_art, n_art = artifact_batch_mean(data, d)
        if (ART / "board_batch" / BOARD[d][1]).exists():
            lat, cnt = board_hist(ART / "board_batch" / BOARD[d][1])
            bq, bmean = hist_quantiles(lat, cnt, np.array(list(REPORT_Q.values())))
            cc += ccdf_rows(d, "board measurement, batch (artifact batch syndromes)", lat=lat, cnt=cnt)
            rows.append(dict(d=d, freq_mhz=f / 1e6, syndromes="artifact batch syndromes", series="board measurement (VMK180, batch)",
                             shots=int(cnt.sum()), a_ns=np.nan, b_ns=np.nan, mean_ns=bmean, **{f"{k}_ns": v for k, v in zip(REPORT_Q, bq)},
                             max_ns=float(lat.max()), ks_vs_board=0.0, ks3pct_vs_board=0.0,
                             artifact_batch_mean_ns=mean_art, artifact_batch_samples=n_art, rel_err_vs_artifact_mean=bmean / mean_art - 1))
        else:
            lat = cnt = None
        for src, label in (("boardbatch", "artifact batch syndromes"), ("board", "artifact stream syndromes")):
            fs = files[(src, d)]
            if not fs.exists():
                continue
            sim = pd.read_csv(fs, keep_default_na=False)
            ok = single_pass(sim, mb.layers_board[d])
            check("counters: one pass, all layers loaded", d, src, "shots violating", int((~ok).sum()))
            check("counters: one pass, all layers loaded", d, src, "shots", len(sim))
            for series, x, (a, b) in [("simulated, hardware only", corrected(sim, f, 0, 0), (0.0, 0.0))] + \
                    [(f"simulated, with replayed CPU timeline ({nm})", corrected(sim, f, *ps[d]), ps[d]) for nm, ps in sets]:
                s = summary(x)
                same = src == "boardbatch"
                if lat is not None:
                    s["ks_vs_board"] = ks_vs_board(x, lat, cnt)
                    s["ks3pct_vs_board"] = ks_tolerant(x, lat, cnt)
                cc += ccdf_rows(d, f"{series} ({label})", x=x)
                rows.append(dict(d=d, freq_mhz=f / 1e6, syndromes=label + (" (same as the batch histogram)" if same else " (other samples, same noise)"),
                                 series=series, used=(series.endswith(f"({BATCH_TIMELINE})") if pb else "stream-mode" in series), shots=len(x), a_ns=a, b_ns=b,
                                 role=("fit" if (d == 9 and "batch fit" in series and same) else "validation" if same else "other samples"),
                                 artifact_batch_mean_ns=mean_art, artifact_batch_samples=n_art,
                                 rel_err_vs_artifact_mean=s["mean_ns"] / mean_art - 1, **s))
    # ---- batch vs stream on identical syndromes (board: stream folder's syndromes; ours: E2)
    for src in ("board", "ours"):
        for d in (9, 13):
            fb, fs = files[(src, d)], L2 / f"sim_{src}_d{d}_p0.001.csv.gz"
            if not (fb.exists() and fs.exists()):
                continue
            bt = pd.read_csv(fb, keep_default_na=False).set_index("shot")
            st = pd.read_csv(fs, keep_default_na=False).set_index("shot")
            j = bt[["cycles", "total_resolve"]].join(st[["cycles", "total_resolve"]], how="inner", lsuffix="_batch", rsuffix="_stream")
            bad = j.cycles_batch < j.cycles_stream
            check("ordering: batch hardware latency >= stream remainder", d, src, "shots", len(j))
            check("ordering: batch hardware latency >= stream remainder", d, src, "shots violating", int(bad.sum()))
            check("ordering: batch hardware latency >= stream remainder", d, src, "violating: no CPU resolution in batch, stream longer by <= 3 cycles",
                  int((bad & (j.total_resolve_batch == 0) & (j.cycles_stream - j.cycles_batch <= 3)).sum()))
            check("ordering: batch hardware latency >= stream remainder", d, src, "violating: more CPU resolutions in stream than in batch (fusion re-work)",
                  int((bad & (j.total_resolve_stream > j.total_resolve_batch)).sum()))
            check("ordering: batch hardware latency >= stream remainder", d, src, "mean CPU resolutions per shot, batch", float(j.total_resolve_batch.mean()))
            check("ordering: batch hardware latency >= stream remainder", d, src, "mean CPU resolutions per shot, stream", float(j.total_resolve_stream.mean()))
            check("ordering: batch hardware latency >= stream remainder", d, src, "ratio of means (batch / stream)", float(j.cycles_batch.mean() / j.cycles_stream.mean()))
            check("ordering: batch hardware latency >= stream remainder", d, src, "shots equal", int((j.cycles_batch == j.cycles_stream).sum()))
    for d in (9, 13):    # the stream rerun with the matching print must reproduce the stream run (deterministic simulation)
        fr, fs = L2 / f"sim_ours_d{d}_p0.001_rerun.csv.gz", L2 / f"sim_ours_d{d}_p0.001.csv.gz"
        if fr.exists() and fs.exists():
            rr = pd.read_csv(fr, keep_default_na=False).set_index("shot"); st = pd.read_csv(fs, keep_default_na=False).set_index("shot")
            j = rr[["cycles", "iterations"]].join(st[["cycles", "iterations"]], how="inner", lsuffix="_rerun", rsuffix="_stream")
            check("reproducibility: stream rerun = stream run", d, "ours", "shots", len(j))
            check("reproducibility: stream rerun = stream run", d, "ours", "shots differing (cycles or iterations)",
                  int(((j.cycles_rerun != j.cycles_stream) | (j.iterations_rerun != j.iterations_stream)).sum()))
    # ---- our syndromes: batch rows (sec. 8 schema), decoder microblossombatch
    for d in (9, 13):
        fs = files[("ours", d)]
        if not fs.exists():
            continue
        sim = pd.read_csv(fs, keep_default_na=False)
        ok = single_pass(sim, mb.layers_ours[d])
        check("counters: one pass, all layers loaded", d, "ours", "shots violating", int((~ok).sum()))
        check("counters: one pass, all layers loaded", d, "ours", "shots", len(sim))
        f = BOARD[d][0]
        a, b = use[d]
        t = corrected(sim, f, a, b)
        cc += ccdf_rows(d, "simulated, with replayed CPU timeline (E2 syndromes)", x=t)
        cid = f"fpga/microblossombatch/surface/d{d}/p0.001"
        frames = []
        for cn in ("cycles", "post_find", "post_resolve", "total_find", "total_resolve", "instructions"):
            frames.append(pd.DataFrame({"config_id": cid, "platform": "fpga", "method": "simulated", "decoder": "microblossombatch",
                                        "code": "surface", "d": d, "p": 0.001, "rounds": d, "shot": sim.shot, "rep": 1,
                                        "counter_name": cn, "counter_value": sim[cn].astype(np.int64), "time_ns": np.round(t, 1),
                                        "hard_bound_ns": "", "logical_error": "", "logical_flips": "",
                                        "timing_method": "simulated_board_corrected", "source": SOURCE_BATCH}))
        out = data.raw / f"fpga_sim_microblossombatch_surface_d{d}_p0.001.csv.gz"
        pd.concat(frames, ignore_index=True).sort_values("shot", kind="stable").to_csv(out, index=False, compression="gzip")
        s = summary(t)
        print(f"{cid}: {len(t)} shots, mean {s['mean_ns']:.0f} ns, p99 {s['p99_ns']:.0f}, p99.9 {s['p999_ns']:.0f}, max {s['max_ns']:.0f}")
    val = pd.DataFrame(rows)
    val.to_csv(data.stats / "level2_batch_validation.csv", index=False, float_format="%.6g")
    pd.DataFrame(cc).to_csv(data.stats / "level2_batch_ccdf.csv", index=False, float_format="%.6g")
    pd.DataFrame(chk).to_csv(data.stats / "level2_batch_checks.csv", index=False, float_format="%.6g")
    if len(val):
        print(val[["d", "syndromes", "series", "shots", "mean_ns", "p50_ns", "p99_ns", "p999_ns", "max_ns", "rel_err_vs_artifact_mean"]
                  + [c for c in ("ks_vs_board", "ks3pct_vs_board") if c in val]].to_string(index=False, float_format=lambda v: f"{v:.3g}"))
    if chk:
        print(pd.DataFrame(chk).to_string(index=False))

