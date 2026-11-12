"""Statistics of the simulation runs, in tidy form.

sim/stats/summary_long.csv          one row per (configuration, cycle class, statistic) for the sweeps
sim/stats/summary.csv               wide pivot: one row per (configuration, cycle class)
sim/stats/checks_summary[_long].csv the same for sim/raw/checks (anchors, grid diagonal)
sim/stats/edge_summary[_long].csv   the same for sim/raw/edge (N1's families at the saturation edge)
sim/stats/ports.csv                 one row per (configuration, port) of the sweeps: offered load, largest queue
sim/stats/grid_diagonal.csv         R x L grid diagonal: simulated p99.9 crossing next to the bound's
sim/stats/anchor1.csv               saturation anchor runs (84 B every 500 ns): stability, growth, p99.9

Cycle class "steady" (non-burst cycles) or "burst" (S3 burst cycles). A configuration is unstable when a
port's offered load (service time of the recorded frames / recorded time) reaches one; it gets no timing
statistics, only its queue growth per cycle.
"""
from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np
import pandas as pd

from . import parameters as P
from .calculus import bound, crossing
from .configuration import Config
from .data import DataDir
from .links import link

TIMING = ["mean_ns", "median_ns", "p90_ns", "p99_ns", "p999_ns", "max_ns", "min_ns", "std_ns"]
KEYS = ["config_id", "topology", "link", "scenario", "aggregation", "Q_c", "N", "cycle_ns"]
SETS = [("", "summary"), ("checks", "checks_summary"), ("edge", "edge_summary")]


def timing_stats(t: np.ndarray) -> dict[str, float]:
    """The timing statistics of the decoder experiment, for round-completion times."""
    q = np.quantile(t, [0.5, 0.9, 0.99, 0.999])
    return dict(mean_ns=float(t.mean()), median_ns=float(q[0]), p90_ns=float(q[1]), p99_ns=float(q[2]),
                p999_ns=float(q[3]), max_ns=float(t.max()), min_ns=float(t.min()),
                std_ns=float(t.std(ddof=1)) if len(t) > 1 else 0.0)


def summarise(raw: Path) -> tuple[list[dict], list[dict]]:
    """Long rows and port rows of one raw file."""
    df = pd.read_csv(raw)
    meta = json.loads((raw.parent / "meta" / raw.name.replace(".csv.gz", ".json")).read_text())
    first = df.iloc[0]
    key = {k: first[k] for k in KEYS}
    cfg = Config.from_id(key["config_id"], float(first["cycle_ns"]))
    key.update(Q_total=int(first["N"]) * int(first["Q_c"]), k=cfg.fan_in)
    load = max(p["offered_load"] for p in meta["ports"])
    stable = load < 1.0
    rc = df["round_completion_ns"].to_numpy()
    growth = float(np.polyfit(df["cycle"].to_numpy(), rc, 1)[0]) if len(rc) > 1 else 0.0
    b = bound(cfg)
    common = dict(offered_load=load, stable=int(stable), cycles_recorded=len(df), seed=int(first["seed"]),
                  max_queue_frames=int(df["max_queue_frames"].max()),
                  utilisation_mean=float(df["utilisation"].mean()), utilisation_max=float(df["utilisation"].max()),
                  bound_utilisation=b["utilisation"], bound_stable=b["stable"])
    rows = []
    classes = [("steady", df["burst"] == 0)] + ([("burst", df["burst"] == 1)] if df["burst"].any() else [])
    for cname, mask in classes:
        stats = dict(common)
        stats["bound_ns"] = b[f"bound_{cname}_ns"] if b["stable"] else math.nan   # the bound of this cycle class
        t = rc[mask.to_numpy()]
        if stable:
            stats.update(timing_stats(t))
            stats["range_ns"] = float(t.max() - t.min())
            if cfg.scenario == "S3" and cname == "steady":  # determinism by phase within the burst period
                ph = df.loc[mask, "cycle"].to_numpy() % cfg.d
                stats["range_by_phase_ns"] = float(max(t[ph == p].max() - t[ph == p].min() for p in np.unique(ph)))
            stats["bound_over_max"] = stats["bound_ns"] / stats["max_ns"]
        else:
            stats["queue_growth_ns_per_cycle"] = growth
        rows += [dict(key, cycle_class=cname, statistic=s, value=v) for s, v in stats.items()]
    ports = [dict(config_id=key["config_id"], **p) for p in meta["ports"]]
    return rows, ports


def collect(folder: Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    rows, ports = [], []
    for raw in sorted(folder.glob("*.csv.gz")):
        r, p = summarise(raw)
        rows += r
        ports += p
    return pd.DataFrame(rows), pd.DataFrame(ports)


def grid_diagonal(wide: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for (top, name), g in wide[wide["link"].str.startswith("G")].groupby(["topology", "link"]):
        ln = link(name)
        for budget_name, budget in P.BUDGETS_NS.items():
            ok = g[(g["stable"] == 1) & (g["p999_ns"] < budget)]
            n_bound, limit = crossing(lambda n: Config(top, name, "S1", 0, 64, n), budget)
            rows.append(dict(topology=top, R_gbps=ln.rate_bps / 1e9, L_ns=ln.latency_ns, scenario="S1", Q_c=64,
                             budget=budget_name, N_cross_bound=n_bound, limit=limit,
                             N_cross_sim_p999=int(ok["N"].max()) if len(ok) else 0,
                             N_tested=" ".join(str(n) for n in sorted(g["N"]))))
    return pd.DataFrame(rows)


def anchor1(wide: pd.DataFrame) -> pd.DataFrame:
    a = wide[wide["scenario"].str.contains("Tc500")]
    cols = ["topology", "link", "N", "cycle_ns", "stable", "offered_load", "queue_growth_ns_per_cycle", "p999_ns",
            "max_ns", "bound_ns"]
    return a[[c for c in cols if c in a.columns]].sort_values(["topology", "link", "N"])


def write_stats(data: DataDir) -> None:
    data.stats.mkdir(parents=True, exist_ok=True)
    for subfolder, name in SETS:
        folder = data.runs_folder(subfolder)
        if not list(folder.glob("*.csv.gz")):
            continue
        long, ports = collect(folder)
        long.to_csv(data.stats / f"{name}_long.csv", index=False)
        idx = KEYS + ["Q_total", "k", "cycle_class"]
        wide = long.set_index(idx + ["statistic"])["value"].unstack("statistic").reset_index()
        wide.to_csv(data.stats / f"{name}.csv", index=False)
        if name == "summary":
            ports.to_csv(data.stats / "ports.csv", index=False)
        elif name == "checks_summary":
            grid_diagonal(wide).to_csv(data.stats / "grid_diagonal.csv", index=False)
            anchor1(wide).to_csv(data.stats / "anchor1.csv", index=False)
        print(f"{name}: {long['config_id'].nunique()} configurations, {len(long)} rows")
