"""The simulated configurations, in four sets, and how many cycles each runs."""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Callable

from . import parameters as P
from .calculus import crossing
from .configuration import Config
from .links import grid_link_name


def cycles(cfg: Config) -> tuple[int, int]:
    """(warm-up, recorded) cycles: more where the latency is random, two extra burst periods in S3."""
    if cfg.link_spec.has_jitter:
        return P.WARMUP_CYCLES, (P.JITTER_CYCLES_SMALL_N if cfg.n <= P.JITTER_SMALL_N else P.JITTER_CYCLES)
    return P.WARMUP_CYCLES, P.RECORDED_CYCLES + (2 * cfg.d if cfg.scenario == "S3" else 0)


def s1_jobs() -> list[Config]:
    """The S1 sweep, Q_c = 16 and 256 on T2 at 10GbE, and the ms case."""
    jobs = []
    for top, links in P.TOPOLOGY_LINKS.items():
        for link in links:
            for agg in P.TOPOLOGY_AGGREGATION[top]:
                for n in P.N_VALUES:
                    jobs.append(Config(top, link, "S1", agg, 64, n))
                    if (top, link) == ("T2", "L5-10G"):
                        jobs += [Config(top, link, "S1", agg, q_c, n) for q_c in (16, 256)]
    jobs += [Config("T2", "L5-10G", "S1", 0, 64, n, cycle_ns=P.MS_CYCLE_NS, tag="Tc41.9ms") for n in P.N_VALUES]
    return jobs


def s3_jobs() -> list[Config]:
    """The S3 burst sweep, with the d sweep on T2 at 10GbE and on T3 over L2."""
    jobs = []
    for top in P.S3_TOPOLOGIES:
        for link in P.TOPOLOGY_LINKS[top]:
            ds = P.S3_D_SWEEP.get((top, link), [P.SCENARIOS["S3"]["d"]])
            for agg in P.TOPOLOGY_AGGREGATION[top]:
                for d in ds:
                    for n in P.N_VALUES:
                        jobs.append(Config(top, link, "S3", agg, 64, n, d=d))
                        if (top, link) == ("T2", "L5-10G") and d == P.SCENARIOS["S3"]["d"]:
                            jobs += [Config(top, link, "S3", agg, q_c, n, d=d) for q_c in (16, 256)]
    return jobs


def check_jobs() -> list[Config]:
    """The saturation anchor, the single-hop anchors and the diagonal of the R x L grid."""
    jobs = []
    # saturation anchor: Sakata et al.'s 84 B every 500 ns, aggregation off, dense N
    for top, link in [("T2", "L5-10G"), ("T2", "L5-100G"), ("T4", "L6-10G"), ("T4", "L6-100G")]:
        n_max = 20 if link.endswith("-10G") else 100
        ns = sorted(set(range(1, n_max + 1)) | {8, 16, 32, 64, 128})
        jobs += [Config(top, link, "S1", 0, 64, n, cycle_ns=P.ANCHOR_CYCLE_NS, frame_bits=P.ANCHOR_FRAME_BITS,
                        tag="Tc500-84B") for n in ns]
    # single hops: one controller on one L3 link into the root (Liu et al.'s measured leaf-to-root link),
    # and T3 on L3 with a single controller for comparison (T1 on L4 is part of the S1 sweep)
    jobs += [Config("T1", "L3", "S1", 0, 64, 1, tag="single-hop"), Config("T3", "L3", "S1", 0, 64, 1)]
    # R x L grid: the diagonal cells, at and just above the bound's crossing for both budgets
    for top in P.GRID_TOPOLOGIES:
        for rate, latency in P.GRID_DIAGONAL:
            link = grid_link_name(rate, latency)
            ns = set()
            for budget in P.BUDGETS_NS.values():
                n_cross, _ = crossing(lambda n: Config(top, link, "S1", 0, 64, n), budget)
                ns |= {max(n_cross, 1), n_cross + 1}
            jobs += [Config(top, link, "S1", 0, 64, n) for n in sorted(ns)]
    return jobs


def edge_jobs() -> list[Config]:
    """N1's families (S1, Q_c = 64, 1.1 us) at the largest stable N of the bound and at the next N, for
    every family that saturates within the swept range; a set of its own, so that the sweep's counts
    and statistics stay as they are."""
    jobs = []
    for top, link in P.N1_LINKS.items():
        for agg in P.TOPOLOGY_AGGREGATION[top]:
            n_stable, limit = crossing(lambda n: Config(top, link, "S1", agg, 64, n), math.inf, n_max=max(P.N_VALUES))
            if limit == "throughput":
                jobs += [Config(top, link, "S1", agg, 64, n) for n in (n_stable, n_stable + 1)]
    return jobs


@dataclass(frozen=True)
class JobSet:
    name: str
    folder: str                     # subfolder of sim/raw, "" for sim/raw itself
    jobs: Callable[[], list[Config]]
    summary: str                    # name of its statistics tables in sim/stats


JOB_SETS = {s.name: s for s in [
    JobSet("checks", "checks", check_jobs, "checks_summary"),
    JobSet("s1", "", s1_jobs, "summary"),
    JobSet("s3", "", s3_jobs, "summary"),
    JobSet("edge", "edge", edge_jobs, "edge_summary"),
]}
