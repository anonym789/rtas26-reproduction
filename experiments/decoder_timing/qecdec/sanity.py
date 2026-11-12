"""SANITY.md: the plausibility checks with the numbers behind each (speed anchor, logical error rate against d,
PyMatching against detector count, post-processor trigger fraction, call-overhead floor, seed check, stability
rerun, interference estimate)."""
from __future__ import annotations

import datetime as dt
import glob
from pathlib import Path

import numpy as np
import pandas as pd

from . import parameters as P
from .data import DataDir
from .grid import GridPoint


def load(path: Path) -> pd.DataFrame | None:
    return pd.read_csv(path) if path.exists() else None


def anchor_check(data: DataDir, lines: list[str]) -> bool:
    A = P.ANCHOR
    ok_any = False
    results = []
    for label, sub in (("sweep (boost off, governor performance)", None),
                       ("boost off", "anchor_boost_off"), ("boost on", "anchor_boost_on")):
        f = data.campaign_raw_file(A["decoder"], GridPoint(A["code"], A["d"], A["p"]), sub)
        if not f.exists():
            continue
        r = pd.read_csv(f)
        first = r[r.rep == 1]["time_ns"]
        per_round = first.mean() / A["d"]
        passed = per_round <= P.ANCHOR_PER_ROUND_NS * P.ANCHOR_TOLERANCE
        ok_any |= passed and sub is None
        ghz = ""
        if r["cycles"].notna().any():
            ghz = f", {(r['cycles'] / r['time_ns']).mean():.2f} GHz from cycles"
        results.append(f"- {label}: mean {first.mean():.0f} ns/shot = **{per_round:.0f} ns/round** "
                       f"(limit {P.ANCHOR_PER_ROUND_NS * P.ANCHOR_TOLERANCE:.0f}){ghz} -> {'PASS' if passed else 'FAIL'}")
    lines.append(f"## 1. Speed anchor: PyMatching, surface code d={A['d']}, p={A['p']:g}, native timing")
    lines.extend(results or ["- no anchor run found"])
    lines.append("")
    return ok_any


def write_report(data: DataDir, report: Path, anchor_only: bool = False) -> bool:
    """Write the report; returns whether the anchor passed (the campaign stops otherwise)."""
    lines = ["# Sanity checks of the decoder timing experiment", "", f"Generated {dt.datetime.now().isoformat(timespec='minutes')}.", ""]
    anchor_ok = anchor_check(data, lines)
    if anchor_only:
        report.write_text("\n".join(lines) + "\n")
        print("\n".join(lines))
        return anchor_ok

    wide = load(data.stats / "summary_wide.csv")
    status = {"anchor": anchor_ok}
    if wide is None:
        lines.append("no stats/summary_wide.csv yet")
        report.write_text("\n".join(lines) + "\n")
        return anchor_ok
    idx = load(data.campaign_index)

    # 2. LER decreases with d at p = 1e-3 (per code and decoder)
    lines.append("## 2. Logical error rate decreases with d at p = 1e-3 (per block)")
    ok = True
    for (code, dec), g in wide[np.isclose(wide.p, 1e-3)].sort_values("d").groupby(["code", "decoder"]):
        ler = g["logical_error_rate"].to_numpy(); ds = g["d"].to_numpy(); n = g["shots"].to_numpy()
        sig = np.sqrt(np.maximum(ler * (1 - ler) / n, 1.0 / n))
        rises = [(ds[i], ler[i - 1], ler[i]) for i in range(1, len(ler)) if ler[i] > ler[i - 1] + 2 * (sig[i] + sig[i - 1])]
        dec_ok = not rises
        ok &= dec_ok
        lines.append(f"- {code} / {dec}: " + ", ".join(f"d{int(dd)}={l:.2e}" for dd, l in zip(ds, ler)) +
                     (" -> PASS" if dec_ok else f" -> FAIL (rises at d={[r[0] for r in rises]})"))
    status["ler_monotone"] = ok
    lines.append("")

    # 3. PyMatching mean time ~ linear in number of detectors (surface)
    lines.append("## 3. PyMatching (surface) mean time vs number of detectors")
    pm = wide[(wide.decoder == "pymatching") & (wide.code == "surface")].merge(
        idx[idx.code == "surface"][["d", "p", "num_detectors"]], on=["d", "p"])
    ok = True
    for p, g in pm.groupby("p"):
        g = g[g.d >= 5]
        if len(g) < 3:
            continue
        slope, _ = np.polyfit(np.log(g["num_detectors"]), np.log(g["mean_ns"]), 1)
        r = np.corrcoef(g["num_detectors"], g["mean_ns"])[0, 1]
        p_ok = 0.8 <= slope <= 1.3
        ok &= p_ok
        lines.append(f"- p={p:g}: log-log slope {slope:.2f} (1 = linear), Pearson r {r:.3f} (d >= 5) -> {'PASS' if p_ok else 'FAIL'}")
    status["pm_linear"] = ok
    lines.append("")

    # 4. post-processor trigger fraction increases with p and with d (per code)
    lines.append("## 4. BP+OSD / BP+LSD trigger fraction increases with p and with d")
    ok = True
    found = False
    for (code, dec), bo in wide[wide.decoder.isin(["bposd", "bplsd"])].groupby(["code", "decoder"]):
        if "osd_trigger_fraction" not in bo or bo.osd_trigger_fraction.isna().all():
            continue
        found = True
        piv = bo.pivot(index="d", columns="p", values="osd_trigger_fraction").sort_index()
        with_p = all((row.diff().dropna() >= -0.01).all() for _, row in piv.iterrows())
        with_d = all((piv[c].diff().dropna() >= -0.01).all() for c in piv.columns) if len(piv) > 1 else True
        c_ok = with_p and with_d
        ok &= c_ok
        lines.append(f"### {code} / {dec}\n```\n" + piv.round(4).to_string() + "\n```")
        lines.append(f"- monotone in p: {with_p}; monotone in d: {with_d} -> {'PASS' if c_ok else 'FAIL'}")
    status["osd_monotone"] = ok and found
    lines.append("")

    # 5. overhead floor
    lines.append("## 5. All-zero-syndrome call-overhead floor")
    fl = load(data.stats / "overhead_floor.csv")
    ok = False
    if fl is not None:
        py = fl[fl.timing_method != "native"]
        ok = len(py) > 0 and py["floor_ns"].notna().all()
        for (code, dec), g in fl.groupby(["code", "decoder"]):
            lines.append(f"- {code} / {dec} ({g.timing_method.iloc[0]}): floor {g.floor_ns.min():.0f}-{g.floor_ns.max():.0f} ns over {len(g)} runs"
                         + (f"; batch-timed points: {sorted(set(g[g.timing_method == 'batch'].d))}" if (g.timing_method == 'batch').any() else ""))
        lines.append(f"- reported for every Python-timed run: {'PASS' if ok else 'FAIL'} (full table stats/overhead_floor.csv)")
    status["floor"] = ok
    lines.append("")

    # 6. seed check
    dec, code, d, p = P.SEED_CHECK_POINT
    lines.append(f"## 6. Seed check: {dec}, {code} d={d}, p={p:g} with a different seed")
    f1, f2 = data.campaign_raw_file(dec, GridPoint(code, d, p)), data.campaign_raw_file(dec, GridPoint(code, d, p), "seedcheck")
    ok = False
    if f1.exists() and f2.exists():
        m1 = pd.read_csv(f1).query("rep == 1")["time_ns"].mean()
        m2 = pd.read_csv(f2).query("rep == 1")["time_ns"].mean()
        rel = abs(m2 - m1) / m1
        ok = rel < 0.05
        lines.append(f"- mean_ns {m1:.0f} vs {m2:.0f} (other seed): {rel:.2%} -> {'PASS' if ok else 'FAIL'}")
    else:
        lines.append("- seed-check run missing")
    status["seed"] = ok
    lines.append("")

    # 7. stability
    lines.append("## 7. Stability rerun at a different time of day (p99.9 within 10 %)")
    ok = True
    found = False
    for dec, code, d, p in P.STABILITY_POINTS:
        base = data.campaign_raw_file(dec, GridPoint(code, d, p))
        reruns = sorted(glob.glob(str(data.campaign_raw / "stability" / "*" / base.name)))
        if not base.exists() or not reruns:
            continue
        found = True
        t0 = pd.read_csv(base).query("rep == 1")["time_ns"]
        for rr in reruns:
            t1 = pd.read_csv(rr).query("rep == 1")["time_ns"]
            q0, q1 = t0.quantile(0.999), t1.quantile(0.999)
            rel = abs(q1 - q0) / q0
            pt_ok = rel <= 0.10
            ok &= pt_ok
            ts = Path(rr).parent.name
            lines.append(f"- {dec} {code} d={d} p={p:g}: p99.9 {q0:.0f} ns (main) vs {q1:.0f} ns ({ts}): {rel:.1%} -> {'PASS' if pt_ok else 'FAIL'}")
    if not found:
        ok = False
        lines.append("- no stability rerun found (raw/stability/<timestamp>/)")
    status["stability"] = ok
    lines.append("")

    s = load(data.stats / "summary.csv")
    if s is not None:
        gap = s[(s.basis == "min") & (s.statistic == "interference_estimate_fraction")]
        lines.append("## Interference estimate (mean first pass vs mean per-shot minimum)")
        for (code, dec), g in gap.groupby(["code", "decoder"]):
            lines.append(f"- {code} / {dec}: {g.value.median():.1%} median, {g.value.max():.1%} max over grid points")
        lines.append("")

    lines.insert(4, "| check | result |\n|---|---|\n" + "\n".join(f"| {k} | {'PASS' if v else 'FAIL'} |" for k, v in status.items()) + "\n")
    report.write_text("\n".join(lines) + "\n")
    print("\n".join(lines))
    return anchor_ok

