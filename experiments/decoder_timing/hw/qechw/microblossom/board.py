"""The board correction of the cycle-accurate simulation.

The Verilator simulation counts accelerator clock cycles from "last syndrome layer ready" to "decoding finished"
with the CPU modelled as instantaneous. On the board (Xilinx VMK180, ARM Cortex-A72) every CPU-accelerator
transaction costs real bus latency and the primal module costs real CPU time. With round-wise fusion one syndrome
layer arrives every 1 us; the CPU loop handles each layer in one iteration (load, obstacle reads, resolutions),
every iteration costs W_i = a + b r_i (r_i = obstacles resolved in iteration i), and an iteration cannot start
before its layer is ready (T_i = (layers loaded - 1) x 1 us), so CPU work on earlier layers can still be running
when the last layer arrives (spill). Replaying this single-server timeline on the per-iteration counts gives

  L_board = cycles / f + spill + a + b r_final
  spill   = max(0, max_i [T_i + sum_{j >= i, j < final} W_j] - T_final)

  a  cost of an iteration without resolution (obstacle read and load instruction on the real bus)
  b  cost per obstacle resolved by the CPU (128-bit read + primal work + instruction writes)

In batch mode (block at once) every shot has a single loop iteration entered with all layers loaded, so the spill
term is zero: L_board = cycles / f + a + b r.
"""
from __future__ import annotations

import re
from pathlib import Path

import numpy as np
import pandas as pd

QS = np.array([0.01, 0.05, 0.1, 0.25, 0.5, 0.75, 0.9, 0.95, 0.98, 0.99, 0.995, 0.998, 0.999, 0.9995, 0.9999])
REPORT_Q = {"p50": 0.5, "p90": 0.9, "p99": 0.99, "p999": 0.999}
GRID = np.logspace(2, 5, 241)            # 100 ns .. 100 us


def board_hist(path: Path) -> tuple[np.ndarray, np.ndarray]:
    """Latency histogram of the artifact's board benchmark: bin centres (ns) and counts."""
    txt = path.read_text()
    m = re.search(r"latency_benchmarker<lower>([-+e\d.]+)<upper>([-+e\d.]+)<N>(\d+)((?:\[\d+\]\d+)*)\[underflow\](\d+)\[overflow\](\d+)", txt)
    lower, upper, N = float(m.group(1)), float(m.group(2)), int(m.group(3))
    idx, cnt = [], []
    for ele in m.group(4)[1:].split("["):
        i, c = ele.split("]"); idx.append(int(i)); cnt.append(int(c))
    idx, cnt = np.array(idx), np.array(cnt)
    lat = lower * (upper / lower) ** ((idx + 0.5) / N) * 1e9      # bin centre, as latency_of() in the artifact
    return lat, cnt


def hist_quantiles(lat, cnt, qs):
    o = np.argsort(lat); lat, cnt = lat[o], cnt[o]
    cdf = np.cumsum(cnt) / cnt.sum()
    return np.array([lat[np.searchsorted(cdf, q)] for q in qs]), float((lat * cnt).sum() / cnt.sum())


class Timeline:
    """Per-shot non-final iterations as padded arrays for the max-plus replay."""

    def __init__(self, sim: pd.DataFrame, num_layers: int, cycle_ns: float = 1000.0):
        n = len(sim)
        its = [[tuple(int(v) for v in e.split(":")) for e in s.split()] if isinstance(s, str) and s else [] for s in sim.iterations]
        m = max(1, max(len(i) - 1 for i in its))
        self.T = np.full((n, m), -1e18)
        self.cnt = np.zeros((n, m))
        self.R = np.zeros((n, m))
        for k, it in enumerate(its):
            nf = it[:-1]                                   # non-final iterations
            for i, (layers, finds, res) in enumerate(nf):
                self.T[k, i] = (layers - 1) * cycle_ns
                self.cnt[k, i] = len(nf) - i
                self.R[k, i] = sum(r for _, _, r in nf[i:])
        self.t_final = (num_layers - 1) * cycle_ns
        self.has = np.array([len(i) > 1 for i in its])

    def spill(self, a: float, b: float) -> np.ndarray:
        done = (self.T + self.cnt * a + self.R * b).max(axis=1)
        return np.where(self.has, np.maximum(0.0, done - self.t_final), 0.0)


def corrected(sim: pd.DataFrame, f_hz: float, a: float, b: float, tl: Timeline | None = None) -> np.ndarray:
    """Board latency (ns) of every simulated shot for the CPU cost a + b r."""
    base = sim.cycles.to_numpy() / f_hz * 1e9 + a + b * sim.post_resolve.to_numpy()
    return base if tl is None else base + tl.spill(a, b)


def fit(sim, f_hz, bq, tl):
    """a, b minimising the L1 distance of log-latency quantiles QS to the board quantiles bq (coarse grid, then fine)."""
    def search(a_grid, b_grid):
        best = None
        cyc = sim.cycles.to_numpy() / f_hz * 1e9
        r = sim.post_resolve.to_numpy()
        for a in a_grid:
            for b in b_grid:
                x = cyc + a + b * r + tl.spill(a, b)
                err = np.abs(np.log(np.quantile(x, QS)) - np.log(bq)).sum()
                if best is None or err < best[0]:
                    best = (err, a, b)
        return best
    e, a, b = search(np.arange(0, 301, 10.0), np.arange(0, 3001, 50.0))
    return search(np.arange(max(0, a - 10), a + 10.1, 1.0), np.arange(max(0, b - 50), b + 50.1, 5.0))


def ks_vs_board(x: np.ndarray, lat: np.ndarray, cnt: np.ndarray) -> float:
    """Kolmogorov-Smirnov distance between a per-shot sample and the board histogram (evaluated at bin centres)."""
    o = np.argsort(lat); lat, cnt = lat[o], cnt[o]
    fb = np.cumsum(cnt) / cnt.sum()
    fx = np.searchsorted(np.sort(x), lat, side="right") / len(x)
    return float(np.max(np.abs(fx - fb)))


def ks_tolerant(x: np.ndarray, lat: np.ndarray, cnt: np.ndarray, tol: float = 0.03) -> float:
    """Levy-type distance: largest CDF gap that remains after allowing a relative latency shift of +-tol.

    The plain KS statistic is dominated by discrete latency levels (whole clock cycles) that differ by a few
    nanoseconds; with a 3 % tolerance (three histogram bins) only differences in probability mass count."""
    o = np.argsort(lat); lat, cnt = lat[o], cnt[o]
    fb = np.cumsum(cnt) / cnt.sum()
    xs = np.sort(x)
    lo = np.searchsorted(xs, lat / (1 + tol), side="right") / len(xs)
    hi = np.searchsorted(xs, lat * (1 + tol), side="right") / len(xs)
    return float(np.max(np.maximum(0.0, np.maximum(fb - hi, lo - fb))))


def ccdf_rows(d, series, x=None, lat=None, cnt=None):
    """Exceedance probability P(L > t) on a log grid (tidy rows)."""
    if x is not None:
        xs = np.sort(x); ex = 1 - np.searchsorted(xs, GRID, side="right") / len(xs)
    else:
        o = np.argsort(lat); l, c = lat[o], cnt[o]; cum = np.cumsum(c) / c.sum()
        ex = 1 - np.concatenate([[0.0], cum])[np.searchsorted(l, GRID, side="right")]
    return [dict(d=d, series=series, latency_ns=float(g), exceedance=float(e)) for g, e in zip(GRID, ex) if e > 0]


def summary(x: np.ndarray) -> dict:
    out = {"mean_ns": float(np.mean(x))}
    for k, q in REPORT_Q.items():
        out[f"{k}_ns"] = float(np.quantile(x, q))
    out["max_ns"] = float(np.max(x))
    return out
