"""Statistics of the per-shot files in raw/, with the CPU experiment's statistics code.

Reads the per-shot files of the campaign's raw/, <platform>_<method>_<decoder>_<code>_d<d>_p<p>.csv.gz with method
transfer, sim or measured (one row per shot, pass and counter), and writes
  stats/summary.csv        one row per configuration (key columns + the timing statistics)
  stats/summary_long.csv   tidy companion: config_id, ..., basis, statistic, value
  stats/pwcet.csv          GPD fits as in the CPU experiment (threshold p90, stability check, fit_ok);
                              for method = transfer the fit describes the input-induced
                              execution-time distribution, not a pWCET
  stats/counters.csv       one row per (config, counter, statistic)
The CUPTI decomposition of the GPU runs (gpu_cupti_*), the throughput runs (gpu_batch_*) and the run records are
separate measurements and stay out of these statistics. timing_stats and pwcet_rows come from qecdec.stats
(decoder_timing/qecdec, on the Python path).
"""
from __future__ import annotations

import re
from pathlib import Path

import numpy as np
import pandas as pd
from qecdec.stats import pwcet_rows, timing_stats

from .data import DataDir

KEY = ["config_id", "platform", "method", "decoder", "code", "d", "p", "rounds"]


PER_SHOT = re.compile(r"^(fpga|asic|gpu)_(transfer|sim|measured)_.+\.csv\.gz$")


def load(raw: Path) -> pd.DataFrame:
    files = sorted(f for f in raw.iterdir() if PER_SHOT.match(f.name))
    if not files:
        raise SystemExit(f"no per-shot files in {raw}")
    return pd.concat([pd.read_csv(f) for f in files], ignore_index=True)


def write_stats(data: DataDir) -> None:
    raw = load(data.campaign_raw)
    data.stats.mkdir(parents=True, exist_ok=True)
    rows, longrows, pw, pws, crows = [], [], [], [], []
    for keyvals, g in raw.groupby(KEY, sort=False):
        key = dict(zip(KEY, keyvals))
        rounds = int(key["rounds"])
        # per-shot table: time_ns is identical on every counter row of a shot; keep one row per (shot, rep)
        shots = g.drop_duplicates(["shot", "rep"])[["shot", "rep", "time_ns", "hard_bound_ns", "logical_error", "logical_flips", "timing_method", "source"]]
        first = shots[shots.rep == shots.rep.min()].set_index("shot").sort_index()
        bases = {"first": first}
        if shots.rep.nunique() > 1:
            mn = shots.groupby("shot")["time_ns"].min().to_frame().join(first.drop(columns=["time_ns"]))
            bases["min"] = mn
        hb = first["hard_bound_ns"].dropna()
        hard_bound = float(hb.iloc[0]) if len(hb) else np.nan
        calibration = "none"
        if key["method"] == "transfer":
            calibration = "literature-constant"
        elif key["method"] == "measured":
            calibration = "measured"
        elif key["method"] == "simulated" and key["decoder"] == "microblossombatch":
            calibration = ("board-histogram (level 2, batch mode, E4 sec. 14: cycle-accurate simulation + CPU timeline fitted at d = 9 "
                           "to the artifact's batch board histogram, validated against it at d = 13)")
        elif key["method"] == "simulated":
            calibration = "board-histogram (level 2: cycle-accurate simulation + board timeline fitted at d = 9)"
        shot_stats = dict(shots=len(first), reps=int(shots.rep.nunique()),
                          logical_error_rate=float(first["logical_error"].mean()),
                          logical_error_rate_per_logical_qubit=float(first["logical_flips"].mean() / 12) if key["code"] == "bb" else float(first["logical_flips"].mean()),
                          hard_bound_ns=hard_bound, above_hard_bound=int((first["time_ns"] > hard_bound).sum()) if np.isfinite(hard_bound) else 0)
        for k, v in shot_stats.items():
            longrows.append(dict(key, basis="shot", statistic=k, value=v))
        wide = dict(key, timing_method=first["timing_method"].iloc[0], source=first["source"].iloc[0], calibration=calibration, **shot_stats)
        for bname, tab in bases.items():
            t = tab["time_ns"].to_numpy(dtype=float)
            ts = timing_stats(t, rounds)
            for k, v in ts.items():
                longrows.append(dict(key, basis=bname, statistic=k, value=v))
            if bname == "first":
                wide.update(ts)
                wide["hard_bound_per_round_ns"] = hard_bound / rounds if np.isfinite(hard_bound) else np.nan
            m, s = pwcet_rows(dict(key, basis=bname), t, rounds, None)
            if m:
                m["distribution"] = "input-induced execution-time distribution" if key["method"] in ("transfer", "simulated") else "measured execution-time distribution"
                pw.append(m)
            pws.extend(s)
        # counter statistics (one row per counter and statistic)
        for cn, gc in g[g.rep == g.rep.min()].groupby("counter_name"):
            v = gc["counter_value"].to_numpy(dtype=float)
            if cn.startswith("legs_"):          # -1 marks shots without per-leg logging (only the first --log-legs shots are logged)
                v = v[v >= 0]
                if not len(v):
                    continue
            q = np.quantile(v, [0.5, 0.9, 0.99, 0.999])
            for stat, val in (("mean", v.mean()), ("median", q[0]), ("p90", q[1]), ("p99", q[2]), ("p999", q[3]), ("max", v.max()), ("min", v.min())):
                crows.append(dict(key, counter=cn, statistic=stat, value=val))
        rows.append(wide)
    order = ["config_id", "platform", "method", "decoder", "code", "d", "p", "rounds", "shots", "mean_ns", "median_ns", "p90_ns", "p99_ns",
             "p999_ns", "max_ns", "mean_per_round_ns", "p999_per_round_ns", "max_per_round_ns", "hard_bound_ns", "hard_bound_per_round_ns",
             "calibration", "logical_error_rate", "logical_error_rate_per_logical_qubit", "above_hard_bound", "timing_method", "source"]
    df = pd.DataFrame(rows)
    cols = [c for c in order if c in df.columns] + [c for c in df.columns if c not in order]
    df[cols].to_csv(data.stats / "summary.csv", index=False, float_format="%.6g")
    pd.DataFrame(longrows).to_csv(data.stats / "summary_long.csv", index=False, float_format="%.6g")
    pd.DataFrame(pw).to_csv(data.stats / "pwcet.csv", index=False, float_format="%.6g")
    pd.DataFrame(pws).to_csv(data.stats / "pwcet_stability.csv", index=False, float_format="%.6g")
    pd.DataFrame(crows).to_csv(data.stats / "counters.csv", index=False, float_format="%.6g")
    print(f"summary: {len(df)} configs; pwcet: {len(pw)} fits; counters: {len(crows)} rows")
    print(df[[c for c in ["config_id", "shots", "mean_ns", "p999_ns", "max_ns", "mean_per_round_ns", "hard_bound_ns", "logical_error_rate"] if c in df.columns]].to_string(index=False))

