"""Network-calculus bound on the round-completion time, the crossing N, and the path formula."""
from __future__ import annotations

import math
from typing import Callable

from .configuration import Config
from .parameters import AGGREGATION_DELAY_NS
from .topologies import Hop, Node


def bound(cfg: Config) -> dict:
    """Worst-case round-completion time, overall and per cycle class.

    Per hop: aggregate staircase arrival curve of `flows` flows that each release F_j bits at the start
    of cycle j (period P = d with the burst at j = 0 in S3, P = 1 otherwise), shifted left by the delay
    variation J accumulated upstream (output arrival curve of a server with delay in [d_min, d_max] is
    alpha(t + d_max - d_min)); rate-latency service beta(t) = R (t - lat_hi)^+. The last frame of
    cycle j leaves at most lat_hi + max_{i <= j} (flows * sum_{m=i..j} F_m / R - max(0, (j - i) T - J))
    after the start of cycle j (busy-period bound); taken per phase j mod P over a horizon of three
    periods. Hops and node delays are summed per phase. For aligned identical frames this is
    L + N F / R per contended port.
    Returns bound_ns (all cycles), bound_steady_ns (non-burst cycles), bound_burst_ns (burst cycle),
    stable and the largest port utilisation.
    """
    period = cfg.d if cfg.scenario == "S3" else 1
    T = cfg.cycle_ns
    per_phase = [0.0] * period
    jitter, util_max = 0.0, 0.0
    for st in cfg.path:
        if isinstance(st, Node):
            per_phase = [x + st.delay for x in per_phase]
            continue
        steady, burst = cfg.frame_sizes(st.merge)      # frames on this hop (merged after aggregation)
        seq = [burst] + [steady] * (period - 1) if period > 1 else [steady]
        ser = [f / st.rate * 1e9 for f in seq]          # ns per frame of each phase
        util = st.flows * sum(ser) / (period * T)
        util_max = max(util_max, util)
        if util >= 1.0:
            return dict(bound_ns=math.inf, bound_steady_ns=math.inf, bound_burst_ns=math.inf, stable=0,
                        utilisation=util_max)
        dev = [-math.inf] * period
        for j in range(3 * period + 2 + math.ceil(jitter / T)):
            work = 0.0
            for i in range(j, -1, -1):
                work += st.flows * ser[i % period]
                dev[j % period] = max(dev[j % period], work - max(0.0, (j - i) * T - jitter))
        h = [st.lat_hi + x for x in dev]
        per_phase = [a + b for a, b in zip(per_phase, h)]
        jitter += max(h) - (st.lat_lo + min(ser))
    return dict(bound_ns=max(per_phase), bound_steady_ns=max(per_phase[1:]) if period > 1 else per_phase[0],
                bound_burst_ns=per_phase[0], stable=1, utilisation=util_max)


def crossing(make_cfg: Callable[[int], Config], budget_ns: float, n_max: int = 10_000_000,
             key: str = "bound_ns") -> tuple[int | None, str]:
    """Largest N with a stable configuration whose bound stays below the budget.

    make_cfg(N) builds the configuration; key selects the bound (bound_ns, bound_steady_ns,
    bound_burst_ns). Returns (N_cross, limit) with limit "latency", "throughput" or "none";
    N_cross = 0 if even N = 1 misses, None if no N up to n_max misses.
    """
    def ok(n: int) -> bool:
        b = bound(make_cfg(n))
        return b["stable"] == 1 and b[key] < budget_ns

    if not ok(1):
        n_cross = 0
    elif ok(n_max):
        return None, "none"
    else:
        lo, hi = 1, n_max  # ok(lo), not ok(hi); the bound does not decrease with N
        while hi - lo > 1:
            mid = (lo + hi) // 2
            lo, hi = (mid, hi) if ok(mid) else (lo, mid)
        n_cross = lo
    b_next = bound(make_cfg(n_cross + 1))
    return n_cross, ("throughput" if b_next["stable"] == 0 else "latency")


def formula(cfg: Config) -> str:
    """The bound of a fixed-latency configuration as a formula in L, F, R, N and k."""
    path = cfg.path
    parts = []
    for st in path:
        if isinstance(st, Hop):
            f = f"F_{st.merge_sym}" if st.merge > 1 else "F"
            ser = f"{f}/R" if st.flows_sym == "1" else f"{st.flows_sym}*{f}/R"
            parts.append(f"({st.lat_sym} + {ser})" if st.lat_sym else ser)
        elif st.delay_sym:
            parts.append(st.delay_sym)
    ln = cfg.link_spec
    where = []
    if "L_eff" in " ".join(parts):
        where.append("L_eff = L - 84 B/R")
    if ln.has_jitter:
        lo, hi = ln.latency_range_ns
        where.append(f"L = {hi:g} (max of U[{lo:g},{hi:g}])")
    if any("P" == x for x in parts):
        where.append(f"P = {AGGREGATION_DELAY_NS:g}")
    merged = [st for st in path if isinstance(st, Hop) and st.merge > 1]
    if merged:
        where.append(f"F_{merged[0].merge_sym} = one frame with the outcomes of {merged[0].merge_sym} controllers")
    if cfg.topology_spec.rule():
        where.append(cfg.topology_spec.rule())
    if cfg.scenario == "S3":
        where.append(f"F = burst frame every {cfg.d} cycles, sup over the burst period")
    s = " + ".join(parts)
    return s + ("; " + ", ".join(where) if where else "") + "; stable iff flows*F/R < T_c at every port"
