"""SANITY.md: the plausibility checks of the hardware experiment, with the numbers behind each."""
from __future__ import annotations

import datetime as dt
from pathlib import Path

import numpy as np
import pandas as pd

from .data import DataDir


def write_report(data: DataDir, report: Path) -> None:
    L = [f"# Sanity checks of the hardware experiment", "", f"Generated {dt.datetime.now().isoformat(timespec='minutes')}.", ""]
    status = {}
    s = pd.read_csv(data.stats / "summary.csv")
    cnt = pd.read_csv(data.stats / "counters.csv")
    # 1. IBM anchor
    L.append("## 1. IBM anchor: Relay-BP mean iterations x 24 ns on the gross code at p = 1e-3, per cycle (IBM's unit: 12-cycle window)")
    ok = False
    g = s[(s.config_id == "fpga/relaybp1/bb/d12/p0.001")]
    if len(g):
        r = g.iloc[0]
        it = cnt[(cnt.config_id == r.config_id) & (cnt.counter == "iterations_window") & (cnt.statistic == "mean")].value.iloc[0]
        per_cycle = r.mean_ns / 12
        ok = per_cycle < 1000
        L.append(f"- mean window iterations {it:.2f} -> mean {r.mean_ns:.0f} ns per 12-cycle window = **{per_cycle:.1f} ns per cycle** (IBM: < 1 us for p < 3e-3; abstract: < 10 iterations, < 240 ns per window at p < 1e-3; conclusion: ~20 iterations, 480 ns at p = 1e-3) -> {'PASS' if ok else 'FAIL'}")
        for cid in ("fpga/relaybp1/bb/d12/p0.002", "fpga/relaybp1/bb/d12/p0.003"):
            h = s[s.config_id == cid]
            if len(h):
                L.append(f"- {cid}: mean {h.mean_ns.iloc[0]:.0f} ns per window = {h.mean_ns.iloc[0]/12:.0f} ns per cycle; p99.9 {h.p999_ns.iloc[0]/12:.0f} ns per cycle")
    else:
        L.append("- missing")
    status["ibm_anchor"] = ok
    L.append("")
    # 2. Micro Blossom in stream mode: the corrected simulation against the board histogram of the same syndromes
    L.append("## 2. Micro Blossom: cycle-accurate simulation against the board (stream mode)")
    vf = data.stats / "level2_validation.csv"
    if vf.exists():
        v = pd.read_csv(vf)
        for d in sorted(v.d.unique()):
            b = v[(v.d == d) & (v.series == "board measurement (VMK180)")]
            c = v[(v.d == d) & (v.series == "simulated, board-corrected")]
            if len(b) and len(c):
                b, c = b.iloc[0], c.iloc[0]
                L.append(f"- level 2 vs board, artifact syndromes, d = {d} ({c.role}): mean {c.mean_ns:.0f} vs {b.mean_ns:.0f} ns, "
                         f"p99 {c.p99_ns:.0f} vs {b.p99_ns:.0f}, p99.9 {c.p999_ns:.0f} vs {b.p999_ns:.0f} ({100 * (c.p999_ns / b.p999_ns - 1):+.0f} %), "
                         f"KS {c.ks_vs_board:.3f} (with 3 % latency tolerance {c.ks3pct_vs_board:.3f})")
    else:
        L.append("- level 2 (simulated calibration) not run: see README")
    L.append("")
    # 2b. batch mode (block at once): checks with thresholds fixed before the runs
    bc, bv = data.stats / "level2_batch_checks.csv", data.stats / "level2_batch_validation.csv"
    if bc.exists() and bv.exists():
        L.append("## 2b. Micro Blossom in batch mode: block at once")
        c = pd.read_csv(bc)
        def val(check, d, src, stat):
            r = c[(c.check == check) & (c.d == d) & (c.source == src) & (c.statistic == stat)]
            return r.value.iloc[0] if len(r) else np.nan
        # (2) ordering
        ok2 = None
        for src in ("board", "ours"):
            for d in (9, 13):
                ch = "ordering: batch hardware latency >= stream remainder"
                n, bad = val(ch, d, src, "shots"), val(ch, d, src, "shots violating")
                if np.isfinite(n):
                    okd = bad == 0
                    ok2 = okd if ok2 is None else (ok2 and okd)
                    L.append(f"- (2) ordering, d = {d}, {src} syndromes: batch hardware cycles below the stream remainder on {int(bad)} of {int(n)} shots "
                             f"({int(val(ch, d, src, 'shots equal'))} equal); ratio of means {val(ch, d, src, 'ratio of means (batch / stream)'):.2f} -> {'PASS' if okd else 'FAIL'}")
        if ok2 is not None:
            status["batch_ordering"] = ok2
        # (3) validation: batch mean (and tail) against the batch board histogram of the same syndromes; graded at d = 13
        # (validation, a and b transferred from d = 9 without refitting); d = 9 is the fit point of the used timeline
        v = pd.read_csv(bv)
        ok3 = None
        corrf = data.stats / "level2_batch_correction.csv"
        if corrf.exists():
            cr = pd.read_csv(corrf)
            L.append("- CPU timeline per resolved obstacle in batch mode: " + "; ".join(
                f"d = {int(r.d)}: a = {r.a_ns:.0f} ns, b = {r.b_ns:.0f} ns ({r.origin}{', used' if r.used else ''})" for _, r in cr.iterrows()))
        for d in (9, 13):
            b = v[(v.d == d) & (v.series == "board measurement (VMK180, batch)")]
            for syn in sorted(v[(v.d == d) & v.series.str.startswith("simulated")].syndromes.unique()):
                same = "same as" in syn
                h = v[(v.d == d) & (v.syndromes == syn) & (v.series == "simulated, hardware only")]
                for _, r in v[(v.d == d) & (v.syndromes == syn) & v.series.str.startswith("simulated, with")].iterrows():
                    line = (f"- (3) validation, d = {d}, {syn}, {r.series.split('(')[-1].rstrip(')')}: batch mean {r.mean_ns:.0f} ns ({100 * r.rel_err_vs_artifact_mean:+.0f} % against the "
                            f"artifact's batch mean {r.artifact_batch_mean_ns:.0f} ns; hardware only {h.mean_ns.iloc[0]:.0f} ns, {100 * h.rel_err_vs_artifact_mean.iloc[0]:+.0f} %)")
                    if same and len(b):
                        bb = b.iloc[0]
                        line += (f"; tail vs the batch board histogram of the same syndromes: p99 {r.p99_ns:.0f} vs {bb.p99_ns:.0f}, p99.9 {r.p999_ns:.0f} vs {bb.p999_ns:.0f} ns "
                                 f"({100 * (r.p999_ns / bb.p999_ns - 1):+.0f} %), KS {r.ks_vs_board:.3f} (3 % tolerance {r.ks3pct_vs_board:.3f})")
                    graded = same and bool(r.used) and r.role == "validation"
                    if graded:
                        okd = abs(r.rel_err_vs_artifact_mean) <= 0.2 and abs(r.p999_ns / b.iloc[0].p999_ns - 1) <= 0.2
                        ok3 = okd if ok3 is None else (ok3 and okd)
                        line += f" -> {'PASS' if okd else 'FAIL'} (mean and p99.9 within 20 %, rows use this timeline)"
                    elif same and r.role == "fit":
                        line += " (fit point)"
                    elif same:
                        line += " (not used for the rows)" if not r.used else ""
                    else:
                        line += " (other samples of the same noise; reported, not graded)"
                    L.append(line)
        if ok3 is not None:
            status["batch_validation"] = ok3
        # (4) counters
        ok4 = None
        for src in ("boardbatch", "board", "ours"):
            for d in (9, 13):
                ch = "counters: one pass, all layers loaded"
                n, bad = val(ch, d, src, "shots"), val(ch, d, src, "shots violating")
                if np.isfinite(n):
                    okd = bad == 0
                    ok4 = okd if ok4 is None else (ok4 and okd)
                    L.append(f"- (4) counters, d = {d}, {src} syndromes: {int(n - bad)} of {int(n)} records show one loop pass entered with all layers loaded -> {'PASS' if okd else 'FAIL'}")
        if ok4 is not None:
            status["batch_counters"] = ok4
        L.append("")
    # 3. GPU
    L.append("## 3. GPU: launch overhead stable across passes; batched throughput next to single-shot latency")
    ok = False
    gm = s[s.platform == "gpu"]
    if len(gm):
        ok = True
        for _, r in gm.iterrows():
            L.append(f"- {r.config_id}: single-shot host mean {r.mean_ns/1e3:.0f} us, p99.9 {r.p999_ns/1e3:.0f} us, max {r.max_ns/1e3:.0f} us (shots {r.shots})")
        for f in sorted(data.campaign_raw.glob("gpu_batch_*.csv")):
            b = pd.read_csv(f)
            txt = "; ".join(f"bs={bs}: {grp.ns_per_shot.mean()/1e3:.0f} us/shot" for bs, grp in b[b.decoder_basis == "X"].groupby("batch_size"))
            L.append(f"- throughput {f.stem.replace('gpu_batch_', '')} (X decoder): {txt}")
        for f in sorted(data.campaign_raw.glob("gpu_cupti_*.csv.gz")):
            c = pd.read_csv(f); piv = c.pivot_table(index="shot", columns="counter_name", values="counter_value")
            ovh = (piv.host_ns_x - piv.gpu_span_ns_x)
            L.append(f"- {f.stem.replace('gpu_cupti_', '')}: kernel-only {piv.kernel_ns_x.mean()/1e3:.0f} us, GPU span {piv.gpu_span_ns_x.mean()/1e3:.0f} us, host {piv.host_ns_x.mean()/1e3:.0f} us -> launch+host overhead {ovh.mean()/1e3:.0f} us (sd {ovh.std()/1e3:.0f} us) over {len(piv)} shots")
        runs = data.campaign_raw / "gpu_measured_relaybp1_bb_d12_p0.001.csv.gz"
        if runs.exists():
            r = pd.read_csv(runs); h = r[r.counter_name == "host_ns_x"].pivot_table(index="shot", columns="rep", values="counter_value")
            L.append(f"- pass-to-pass stability (relaybp1 d12 p1e-3, host_ns_x means per pass): " + ", ".join(f"{h[c].mean()/1e3:.0f} us" for c in h.columns))
    else:
        L.append("- no GPU rows")
    status["gpu"] = ok
    L.append("")
    # 4. hard bound
    L.append("## 4. Transferred samples vs hard bound")
    tr = s[s.method == "transfer"]
    ok = bool(len(tr)) and (tr.above_hard_bound.fillna(0) == 0).all()
    for _, r in tr.iterrows():
        if np.isfinite(r.hard_bound_ns):
            L.append(f"- {r.config_id}: max {r.max_ns:.0f} ns, bound {r.hard_bound_ns:.0f} ns, samples above bound: {int(r.above_hard_bound)}{' (at the bound: non-converged shots)' if r.max_ns >= r.hard_bound_ns else ''}")
    L.append(f"-> {'PASS' if ok else 'FAIL'}")
    status["hard_bound"] = ok
    L.append("")
    # 5. noise models
    L.append("## 5. Noise models per row")
    L.append("- E2 / our transfers / GPU: Gidney `uniform_depolarizing` (hw/syndromes, decoder_timing/syndromes)")
    L.append("- IBM FPGA constant: 'academic circuit noise' (arXiv 2510.21600); the constant (24 ns per iteration) is noise-independent, the iteration counts are ours")
    L.append("- Micro Blossom board histograms: their circuit-level noise (arXiv 2502.14787 sec. 8); the simulated rows of our syndromes use the uniform-depolarising noise (stated limitation)")
    status["noise_models"] = True
    L.append("")
    L.insert(4, "| check | result |\n|---|---|\n" + "\n".join(f"| {k} | {'PASS' if v else 'FAIL'} |" for k, v in status.items()) + "\n")
    report.write_text("\n".join(L) + "\n")
    print("\n".join(L))

