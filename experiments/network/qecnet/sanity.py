"""SANITY.md: the plausibility checks with their numbers (determinism, seed rerun, anchors, bound against
simulation, stability, R x L grid diagonal). Reads sim/stats, bound/ and, for the unstable configurations
and the seed rerun, sim/raw.
"""
from __future__ import annotations

import datetime as dt
from pathlib import Path

import numpy as np
import pandas as pd

from . import parameters as P
from . import simulation
from .configuration import Config
from .data import DataDir
from .links import LINKS

REL_TOL = 1e-9   # float64 rounding relative to the compared value
ABS_TOL = 1e-6   # ns; raw files carry six decimals
# Float64 rounding of absolute simulation times: one ulp at absolute time T is 2.2e-16 T, and serialising N
# frames accumulates up to N of them (observed: 0.015 ns at T = 1.05e10 ns, N = 16,000, i.e. 1.5e-12 T, in the
# 41.9 ms case). Allowed: 1e-11 T, with T = (warm-up + recorded cycles) x cycle; at the 1.1 us cycle that is
# 2.75e-6 ns, so the 1.1 us sweep is still held to the six decimals of the raw files.
ABS_TIME_REL_TOL = 1e-11
SIM_CYCLES = P.WARMUP_CYCLES + P.RECORDED_CYCLES


def tol(x: float, cycle_ns: float = 0.0) -> float:
    return max(ABS_TOL, REL_TOL * abs(x), ABS_TIME_REL_TOL * cycle_ns * SIM_CYCLES)


def tol_rows(df: pd.DataFrame, col: str) -> pd.Series:
    """tol() per row, with each row's own cycle."""
    return np.maximum(ABS_TOL, np.maximum(REL_TOL * df[col].abs(), ABS_TIME_REL_TOL * df["cycle_ns"] * SIM_CYCLES))


def fmt(x: float, nd: int = 1) -> str:
    return f"{x:,.{nd}f}"


def raw_file(data: DataDir, config_id: str) -> Path:
    return data.runs / f"{Config.from_id(config_id, P.CYCLE_NS).file_stem}.csv.gz"


def check_determinism(data: DataDir, w: pd.DataFrame) -> tuple[str, list[str]]:
    out = []
    det = w[~w["link"].eq("L3")]
    st = det[det["stable"] == 1].copy()
    # in S3 the steady cycles repeat with the burst period (a burst can spill into the next cycles):
    # deterministic means identical at the same phase of the period
    s3_steady = st["scenario"].str.startswith("S3") & (st["cycle_class"] == "steady")
    st["spread_ns"] = st["range_ns"].where(~s3_steady, st["range_by_phase_ns"])
    bad = st[st["spread_ns"] > tol_rows(st, "max_ns")]
    out.append(f"- stable configurations without L3: {st['config_id'].nunique()}; recorded cycles of each class "
               f"identical within max(1e-6 ns, 1e-9 x value, 1e-11 x absolute time): {st['config_id'].nunique() - bad['config_id'].nunique()} "
               f"(S3 steady cycles compared at equal phase of the burst period; largest spread {st['spread_ns'].max():.2g} ns, in "
               f"`{st.loc[st['spread_ns'].idxmax(), 'config_id']}`: float64 rounding at absolute times of "
               f"{st.loc[st['spread_ns'].idxmax(), 'cycle_ns'] * 250:.2g} ns)")
    s3 = st[st["scenario"].str.startswith("S3")]
    if len(s3):
        burst = s3[s3["cycle_class"] == "burst"]
        steady = s3[s3["cycle_class"] == "steady"]
        out.append(f"- S3: {burst['config_id'].nunique()} configurations; burst cycles identical in all "
                   f"(largest spread {burst['range_ns'].max():.2g} ns); steady cycles identical by phase in the "
                   f"burst period in all (largest {steady['range_by_phase_ns'].max():.2g} ns) and identical "
                   f"across phases in {int((steady['range_ns'] <= tol_rows(steady, 'max_ns')).sum())} of "
                   f"{len(steady)} (no spillover of the burst into the following cycle within the sweep)")
    # unstable deterministic configurations: the queue grows by the same amount every cycle
    un = det[(det["stable"] == 0)].drop_duplicates("config_id")
    n_const = 0
    worst = 0.0
    for cid in un["config_id"]:
        rc = pd.read_csv(raw_file(data, cid), usecols=["round_completion_ns"])["round_completion_ns"].to_numpy()
        period = int(cid.split("/")[3].split("-d")[1]) if "/S3-d" in cid else 1
        inc = rc[period:] - rc[:-period]          # growth per burst period (per cycle outside S3)
        spread = inc.max() - inc.min()
        worst = max(worst, spread)
        n_const += spread <= tol(rc.max())
    out.append(f"- unstable configurations without L3: {len(un)}; constant queue growth per cycle (per burst period in S3) in {n_const} "
               f"(largest spread of the per-cycle increment {worst:.2g} ns)")
    ok = bad.empty and n_const == len(un)
    return ("PASS" if ok else "FAIL"), out


def check_seed_rerun(data: DataDir) -> tuple[str, list[str]]:
    """One jittered configuration recomputed from its recorded seed."""
    cfg = Config("T3", "L3", "S1", 0, 64, 8)
    stored = pd.read_csv(raw_file(data, cfg.config_id))
    assert int(stored["seed"].iloc[0]) == cfg.seed
    res = simulation.run(cfg, P.WARMUP_CYCLES, len(stored))
    again = np.array([float("%.6f" % v) for v in res["per_cycle"]["round_completion_ns"]])  # as written
    same = np.array_equal(again, stored["round_completion_ns"].to_numpy())
    return ("PASS" if same else "FAIL"), [f"- `{cfg.config_id}` rerun from seed {cfg.seed}: {len(stored):,} recorded cycles "
                                          f"{'bit-identical' if same else 'DIFFER'} to the stored raw file"]


def check_saturation_anchor(sat: pd.DataFrame, a1: pd.DataFrame) -> tuple[str, list[str]]:
    out, ok = [], True
    s = sat[sat["cycle_ns"] == P.ANCHOR_CYCLE_NS]
    for _, r in s.iterrows():
        out.append(f"- closed form, {int(r.rate_gbps)}GbE: T_c R / F = {r.quotient_TcR_over_F:.2f}, largest stable "
                   f"N = {int(r.largest_stable_N)}, first saturated N = {int(r.first_saturated_N)} "
                   f"(Sakata et al. sec. 2.2: \"{r.sakata_statement}\")")
    sakata = {"10G": 8, "100G": 80}
    lit = []
    for (top, name), g in a1.groupby(["topology", "link"]):
        g = g.sort_values("N")
        st, un = g[g["stable"] == 1], g[g["stable"] == 0]
        first_un = int(un["N"].min())
        growth = float(un.loc[un["N"] == first_un, "queue_growth_ns_per_cycle"].iloc[0])
        sweep = g[g["N"].isin([8, 16, 32, 64, 128])]
        sw_st = sweep[sweep["stable"] == 1]["N"]
        sw_un = sweep[sweep["stable"] == 0]["N"]
        lo = int(sw_st.max()) if len(sw_st) else 0
        hi = int(sw_un.min())
        target = sakata[name.split("-")[1]]
        within = lo < target <= hi
        ok &= within
        grid = (f"on the sweep grid stable at {lo}, unstable at {hi}" if lo else
                f"on the sweep grid unstable already at its first point N = {hi}")
        out.append(f"- simulation, {top} on {name} (aggregation off, dense N): stable up to N = {int(st['N'].max())}, "
                   f"queue grows from N = {first_un} (+{growth:.1f} ns per cycle); {grid}: Sakata's {target} "
                   f"{'lies within this step' if within else 'is OUTSIDE this step'}")
        ok_lat = g[(g["stable"] == 1) & (g["p999_ns"] < P.ANCHOR_CYCLE_NS)]
        lit.append(f"{top}/{name}: largest N with p99.9 < 500 ns = {int(ok_lat['N'].max()) if len(ok_lat) else 0} "
                   f"(p99.9 at N = 1: {fmt(g.loc[g['N'] == 1, 'p999_ns'].iloc[0])} ns)")
    out.append("- literal reading \"the simulation shows the p99.9 crossing the cycle at those N\": **MISS** -- "
               + "; ".join(lit) + ". Cause: not the frame or gap accounting (the saturation points above are exact) "
               "but the fixed latency: the 450 ns aggregator (400 ns assumed switch) alone is 90 % (80 %) of "
               "Sakata's 500 ns cycle, so the p99.9 passes the cycle long before the link saturates; the latency "
               "crossing and the throughput limit are the two different limits of the R x L grid. Nothing was tuned.")
    return ("PASS (saturation); MISS (literal p99.9 reading)" if ok else "FAIL"), out


def check_single_hops(w: pd.DataFrame, chk: pd.DataFrame) -> tuple[str, list[str]]:
    out = []
    l4 = w[(w["topology"] == "T1") & (w["link"] == "L4") & (w["scenario"] == "S1")]
    ok4 = bool(((l4["min_ns"] - 361.6).abs() < 1e-6).all() and ((l4["max_ns"] - 361.6).abs() < 1e-6).all())
    out.append(f"- T1 on L4, S1, all {len(l4)} N: every recorded cycle {fmt(l4['min_ns'].min(), 4)} to "
               f"{fmt(l4['max_ns'].max(), 4)} ns (Bristol: 361.6 ns for a 64 B frame; no serialisation added "
               f"for the first frame) -> {'PASS' if ok4 else 'FAIL'}")
    one = chk[chk["config_id"] == "net/T1/L3/S1@single-hop/agg0/Qc64/N1"].iloc[0]
    ser = 96 / LINKS["L3"].payload_rate_bps * 1e9
    lo, hi = one["min_ns"] - ser, one["max_ns"] - ser
    ok3 = abs(one["mean_ns"] - ser - 157) < 0.5 and lo >= 141 - 1e-6 and hi <= 173 + 1e-6
    out.append(f"- one controller on one L3 link into the root (Liu et al.'s leaf -> root link), "
               f"{int(one['cycles_recorded']):,} cycles: mean {fmt(one['mean_ns'], 2)} ns, range "
               f"[{fmt(one['min_ns'], 2)}, {fmt(one['max_ns'], 2)}] ns = 157 +- 16 ns plus the serialisation of the "
               f"96-bit frame ({ser:.1f} ns at 10 x 64/66 Gb/s); without it: mean {fmt(one['mean_ns'] - ser, 2)}, "
               f"range [{fmt(lo, 2)}, {fmt(hi, 2)}] -> {'PASS' if ok3 else 'FAIL'}. Liu et al. do not state whether "
               f"their 157 ns includes serialisation; the model adds F/R on every link except L4.")
    t3 = chk[chk["config_id"] == "net/T3/L3/S1/agg0/Qc64/N1"]
    if len(t3):
        out.append(f"- for comparison, T3 on L3 with a single controller (controller -> leaf -> root, two L3 hops): "
                   f"mean {fmt(t3['mean_ns'].iloc[0], 1)} ns. \"T3 on L3 with one leaf\" is read as the single "
                   f"hop above, which is Liu et al.'s measured configuration (leaves are the controller boards).")
    return ("PASS" if ok4 and ok3 else "FAIL"), out


def check_bound(w: pd.DataFrame) -> tuple[str, list[str]]:
    st = w[w["stable"] == 1].copy()
    viol = st[st["max_ns"] > st["bound_ns"] + tol_rows(st, "bound_ns")]
    out = [f"- {st['config_id'].nunique()} stable configurations ({len(st)} configuration x cycle-class rows): "
           f"simulated maximum above the bound in {len(viol)}"]
    st["group"] = np.where(st["link"].eq("L3"), st["topology"] + " on L3 (jitter)", st["topology"])
    tab = st.groupby("group")["bound_over_max"].agg(["count", "min", "median", "max"])
    out.append("\nTightness, bound / simulated maximum:\n\n| topology | rows | min | median | max |\n|---|---|---|---|---|")
    for g, r in tab.iterrows():
        out.append(f"| {g} | {int(r['count'])} | {r['min']:.4f} | {r['median']:.4f} | {r['max']:.4f} |")
    out.append("\nThe bound and the simulation share the path model; for aligned, fixed frames the sum of per-hop "
               "deviations is attained (one contended port per path), so deterministic configurations give 1. On L3 "
               "the bound takes the maximum latency 173 ns on every hop and the 32 ns delay variation into the "
               "leaf's arrival curve.")
    return ("PASS" if viol.empty else "FAIL"), out


def check_stability(w: pd.DataFrame) -> tuple[str, list[str]]:
    one = w.drop_duplicates("config_id")
    un = one[one["stable"] == 0].sort_values(["topology", "link", "scenario", "aggregation", "N"])
    agree = bool((one["stable"] == one["bound_stable"]).all())
    out = [f"- {len(one)} configurations, {len(un)} unstable (offered load >= 1 on some port); the bound's "
           f"utilisation condition agrees with the simulation in {'all' if agree else 'NOT all'}; unstable "
           f"configurations carry no timing statistics and are not drawn as latencies (a cross in N1)",
           "\n| configuration | offered load | queue growth (ns per cycle) |\n|---|---|---|"]
    for _, r in un.iterrows():
        out.append(f"| `{r['config_id']}` | {r['offered_load']:.3f} | {r['queue_growth_ns_per_cycle']:,.1f} |")
    return ("PASS" if agree else "FAIL"), out


def check_grid(d: pd.DataFrame) -> tuple[str, list[str]]:
    ok = bool((d["N_cross_bound"] == d["N_cross_sim_p999"]).all())
    out = [f"- {len(d)} cells x budgets (T2 and T4, diagonal R/L = 1/50, 10/100, 25/200, 100/400, 400/800, S1, "
           f"Q_c = 64): simulated p99.9 crossing equals the bound's in {int((d['N_cross_bound'] == d['N_cross_sim_p999']).sum())}"]
    for _, r in d.iterrows():
        out.append(f"  - {r.topology} R = {r.R_gbps:g} Gb/s, L = {r.L_ns:g} ns, {r.budget}: bound {r.N_cross_bound} "
                   f"({r.limit}), simulated {r.N_cross_sim_p999} (N simulated: {r.N_tested})")
    return ("PASS" if ok else "FAIL"), out


def write_report(data: DataDir, report: Path) -> None:
    w = pd.read_csv(data.stats / "summary.csv")
    chk = pd.read_csv(data.stats / "checks_summary.csv")
    a1 = pd.read_csv(data.stats / "anchor1.csv")
    sat = pd.read_csv(data.bound / "saturation.csv")
    diag = pd.read_csv(data.stats / "grid_diagonal.csv")
    checks = [
        ("0. Determinism", *check_determinism(data, w)),
        ("0b. Seed rerun (deterministic given the seed)", *check_seed_rerun(data)),
        ("1. Saturation anchor", *check_saturation_anchor(sat, a1)),
        ("2. Single-hop anchors", *check_single_hops(w, chk)),
        ("3. Bound vs simulation", *check_bound(w)),
        ("4. Utilisation and unstable configurations", *check_stability(w)),
        ("5. R x L grid diagonal by simulation", *check_grid(diag)),
    ]
    lines = ["# Sanity checks of the network experiment", "",
             f"Generated {dt.datetime.now().isoformat(timespec='minutes')} by `python -m qecnet sanity` from "
             "`sim/stats/`, `bound/` and `sim/raw/`.", "", "| check | result |", "|---|---|"]
    lines += [f"| {name} | {res} |" for name, res, _ in checks]
    for name, res, body in checks:
        lines += ["", f"## {name}: {res}", ""] + body
    report.write_text("\n".join(lines) + "\n")
    print("\n".join(f"{n}: {r}" for n, r, _ in checks))
