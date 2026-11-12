"""Statistics and pWCET fits of the raw timing files, in tidy form.

stats/summary.csv          one row per (decoder, code, d, p, basis, statistic); basis "first" = interleaved pass 1,
                           "min" = per-shot minimum over the passes, "shot" = statistics that do not depend on timing
stats/summary_wide.csv     pivot of the first-pass rows plus *_min columns
stats/pwcet.csv            one row per (decoder, d, p, basis): GPD peaks-over-threshold fit above the 90th percentile
stats/pwcet_stability.csv  the fits at all five thresholds (numeric threshold-stability check)
stats/overhead_floor.csv   one row per run: all-zero-syndrome call floor
stats/ecdf.csv             empirical CDF per (decoder, d, p, basis), thinned to ECDF_POINTS quantiles
stats/mean_excess.csv      mean excess above thresholds per (decoder, d, p, basis); for BP+OSD on the
                           OSD-triggered mode only
"""
from __future__ import annotations

import glob
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats as sps

from . import parameters as P
from .data import DataDir

TAIL_PROBS = {"q_1e-6_ns": 1e-6, "q_1e-9_ns": 1e-9}
THRESH_Q = [0.85, 0.875, 0.90, 0.925, 0.95]
MAIN_Q = 0.90
ECDF_POINTS = 400
ME_QUANTILES = np.linspace(0.5, 0.995, 60)


def load_raw(raw: Path) -> pd.DataFrame:
    files = sorted(glob.glob(str(raw / "*.csv.gz")))
    if not files:
        raise SystemExit("no raw files")
    parts = [pd.read_csv(f) for f in files]
    return pd.concat(parts, ignore_index=True)


def per_shot_bases(g: pd.DataFrame) -> dict[str, pd.DataFrame]:
    """Return {basis: per-shot table with time_ns} for first run and per-shot min."""
    first = g[g["rep"] == 1].set_index("shot").sort_index()
    mn = g.groupby("shot")["time_ns"].min().to_frame()
    mn = mn.join(first.drop(columns=["time_ns"]))
    return {"first": first, "min": mn}


def timing_stats(t: np.ndarray, rounds: int) -> dict[str, float]:
    q = np.quantile(t, [0.5, 0.9, 0.99, 0.999])
    out = dict(mean_ns=t.mean(), median_ns=q[0], p90_ns=q[1], p99_ns=q[2], p999_ns=q[3],
               max_ns=t.max(), min_ns=t.min(), std_ns=t.std(ddof=1) if len(t) > 1 else 0.0)
    out.update(mean_per_round_ns=out["mean_ns"] / rounds, p99_per_round_ns=out["p99_ns"] / rounds,
               p999_per_round_ns=out["p999_ns"] / rounds, max_per_round_ns=out["max_ns"] / rounds)
    return out


def gpd_fit(t: np.ndarray, u: float):
    exc = t[t > u] - u
    n_exc = len(exc)
    if n_exc < 30:
        return None
    xi, loc, scale = sps.genpareto.fit(exc, floc=0)
    zeta = n_exc / len(t)
    quantiles = {}
    for name, prob in TAIL_PROBS.items():
        # P(T > x) = zeta * (1 - F_gpd(x - u)) = prob  ->  x = u + isf(prob/zeta)
        quantiles[name] = u + sps.genpareto.isf(prob / zeta, xi, 0, scale) if prob < zeta else np.nan
    mean_excess = exc.mean()
    return dict(threshold_ns=u, shape_xi=xi, scale=scale, n_exceedances=n_exc, exceedance_fraction=zeta,
                mean_excess_ns=mean_excess, **quantiles)


def pwcet_rows(key: dict, t_all: np.ndarray, rounds: int, osd: np.ndarray | None):
    """Fit on the full sample; for BP+OSD / BP+LSD fit the post-processor-triggered mode only."""
    note = ""
    t = t_all
    mode_fraction = 1.0
    if osd is not None and 0 < osd.sum() < len(osd):
        t = t_all[osd == 1]
        mode_fraction = float(osd.mean())
        note = f"tail fitted on OSD-triggered mode only ({mode_fraction:.3%} of shots); exceedance probabilities scaled by that fraction"
    stab, main = [], None
    for q in THRESH_Q:
        u = float(np.quantile(t, q))
        f = gpd_fit(t, u)
        if f is None:
            continue
        # rescale exceedance probability to the whole shot population
        if mode_fraction < 1.0:
            zeta = f["exceedance_fraction"] * mode_fraction
            for name, prob in TAIL_PROBS.items():
                f[name] = u + sps.genpareto.isf(prob / zeta, f["shape_xi"], 0, f["scale"]) if prob < zeta else np.nan
            f["exceedance_fraction"] = zeta
        row = dict(key, basis=key["basis"], threshold_quantile=q, **f)
        stab.append(row)
        if q == MAIN_Q:
            main = dict(row)
    if main is None:
        return None, stab
    shapes = [r["shape_xi"] for r in stab]
    q9 = [r["q_1e-9_ns"] for r in stab if np.isfinite(r["q_1e-9_ns"])]
    shape_range = max(shapes) - min(shapes)
    q9_ratio = (max(q9) / min(q9)) if q9 and min(q9) > 0 else np.inf
    fit_ok = int(main["shape_xi"] <= 0.5 and shape_range <= 0.3 and q9_ratio <= 3.0 and main["n_exceedances"] >= 100)
    main.update(shape_range_p85_p95=shape_range, q1e9_ratio_p85_p95=q9_ratio, fit_ok=fit_ok,
                empirical_max_ns=float(t_all.max()), empirical_max_per_round_ns=float(t_all.max()) / rounds,
                **{"q_1e-9_per_round_ns": main["q_1e-9_ns"] / rounds, "q_1e-6_per_round_ns": main["q_1e-6_ns"] / rounds},
                shots=len(t_all), iid_note="shots are i.i.d. by construction (independent Stim samples); no time-series test applied",
                note=note)
    main.pop("threshold_quantile", None)
    return main, stab


def write_stats(data: DataDir) -> None:
    data.stats.mkdir(parents=True, exist_ok=True)
    raw = load_raw(data.campaign_raw)
    rows, pw, pws, ecdf, me = [], [], [], [], []
    index = pd.read_csv(data.campaign_index) if data.campaign_index.exists() else None
    for (dec, code, d, p), g in raw.groupby(["decoder", "code", "d", "p"]):
        rounds = int(g["rounds"].iloc[0])
        tm = g["timing_method"].iloc[0]
        base = dict(decoder=dec, code=code, d=int(d), p=float(p), rounds=rounds, timing_method=tm)
        num_obs = 1
        if index is not None:
            m = index[(index.code == code) & (index.d == d) & np.isclose(index.p, p)]
            if len(m):
                num_obs = int(m.num_observables.iloc[0])
        bases = per_shot_bases(g)
        shots = len(bases["first"])
        reps = int(g["rep"].max())
        first = bases["first"]
        shot_stats = dict(shots=shots, reps=reps,
                          logical_error_rate=first["logical_error"].mean(),
                          logical_errors=int(first["logical_error"].sum()),
                          num_observables=num_obs,
                          logical_error_rate_per_logical_qubit=first["logical_flips"].mean() / num_obs
                          if "logical_flips" in first else np.nan,
                          mean_n_detections=first["n_detections"].mean())
        if first["osd_triggered"].notna().any():
            shot_stats["osd_trigger_fraction"] = first["osd_triggered"].mean()
        if first["bp_iterations"].notna().any():
            shot_stats["mean_bp_iterations"] = first["bp_iterations"].mean()
            shot_stats["bp_nonconverged_fraction"] = (first["bp_iterations"] >= P.BP_MAX_ITER).mean()
        if first["cycles"].notna().any():
            c = first["cycles"].dropna()
            shot_stats["mean_ghz_from_cycles"] = (c / first.loc[c.index, "time_ns"]).mean()
        for k, v in shot_stats.items():
            rows.append(dict(base, basis="shot", statistic=k, value=v))
        for bname, tab in bases.items():
            t = tab["time_ns"].to_numpy(dtype=float)
            for k, v in timing_stats(t, rounds).items():
                rows.append(dict(base, basis=bname, statistic=k, value=v))
            if bname == "min":
                gap = bases["first"]["time_ns"].mean() - t.mean()
                rows.append(dict(base, basis="min", statistic="interference_estimate_ns", value=gap))
                rows.append(dict(base, basis="min", statistic="interference_estimate_fraction",
                                 value=gap / t.mean() if t.mean() else np.nan))
            osd = tab["osd_triggered"].to_numpy() if dec in ("bposd", "bplsd") else None
            m, s = pwcet_rows(dict(base, basis=bname), t, rounds, osd)
            if m:
                pw.append(m)
            pws.extend(s)
            qs = np.linspace(0, 1, ECDF_POINTS + 1)
            ts = np.quantile(t, qs)
            ecdf.extend(dict(base, basis=bname, time_ns=float(tv), cdf=float(q)) for tv, q in zip(ts, qs))
            tm_ = t[osd == 1] if (osd is not None and osd.sum() > 0) else t
            for q in ME_QUANTILES:
                u = float(np.quantile(tm_, q))
                exc = tm_[tm_ > u]
                if len(exc):
                    me.append(dict(base, basis=bname, quantile=float(q), threshold_ns=u,
                                   mean_excess_ns=float((exc - u).mean()), n_exceedances=int(len(exc))))
    summary = pd.DataFrame(rows)
    summary.to_csv(data.stats / "summary.csv", index=False, float_format="%.6g")
    pd.DataFrame(pw).to_csv(data.stats / "pwcet.csv", index=False, float_format="%.6g")
    pd.DataFrame(pws).to_csv(data.stats / "pwcet_stability.csv", index=False, float_format="%.6g")
    pd.DataFrame(ecdf).to_csv(data.stats / "ecdf.csv", index=False, float_format="%.6g")
    pd.DataFrame(me).to_csv(data.stats / "mean_excess.csv", index=False, float_format="%.6g")

    # convenience wide view: first-run basis plus *_min columns
    keys = ["decoder", "code", "d", "p", "rounds", "timing_method"]
    shot = summary[summary.basis == "shot"].pivot_table(index=keys, columns="statistic", values="value")
    fst = summary[summary.basis == "first"].pivot_table(index=keys, columns="statistic", values="value")
    mn = summary[summary.basis == "min"].pivot_table(index=keys, columns="statistic", values="value").add_suffix("_min")
    wide = shot.join(fst).join(mn).reset_index()
    order = ["decoder", "code", "d", "p", "rounds", "shots", "timing_method", "mean_ns", "median_ns", "p90_ns", "p99_ns",
             "p999_ns", "max_ns", "mean_per_round_ns", "p999_per_round_ns", "max_per_round_ns", "logical_error_rate",
             "logical_error_rate_per_logical_qubit", "mean_n_detections", "osd_trigger_fraction", "mean_bp_iterations"]
    cols = [c for c in order if c in wide.columns] + [c for c in wide.columns if c not in order]
    wide[cols].sort_values(["code", "decoder", "d", "p"]).to_csv(data.stats / "summary_wide.csv", index=False, float_format="%.6g")

    # call-overhead floor per run
    runs = data.campaign_raw / "runs.csv"
    if runs.exists():
        r = pd.read_csv(runs)
        r = r[r["subdir"].isna() | (r["subdir"] == "")]
        r[["decoder", "code", "d", "p", "timing_method", "floor_ns", "pilot_median_ns", "shots_requested", "shots",
           "cycles_available", "core", "governor", "boost", "started", "finished"]].to_csv(
            data.stats / "overhead_floor.csv", index=False)
    print(f"summary: {len(summary)} rows, pwcet: {len(pw)} fits, stability: {len(pws)} rows")

