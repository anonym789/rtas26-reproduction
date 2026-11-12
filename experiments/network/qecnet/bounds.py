"""The bound tables.

bound/bounds.csv       one row per configuration of the sweep (S3 rows carry steady-cycle and burst-cycle
                       bounds separately), and the ms case
bound/crossings.csv    one row per configuration family, budget and cycle class: the largest N whose bound
                       stays below the budget (any integer N, not only the swept values)
bound/grid.csv         R x L grid for T2 and T4, S1 and S2, all Q_c, both budgets (aggregation off)
bound/grid_points.csv  the named links as points on the grid
bound/saturation.csv   saturation condition N F / R < T_c for the anchor and the 1.1 us cycle
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import pandas as pd

from . import parameters as P
from .calculus import bound, crossing, formula
from .configuration import Config
from .data import DataDir
from .links import LINKS, grid_link_name


@dataclass(frozen=True)
class Family:
    """Configurations that differ only in N."""
    topology: str
    link: str
    scenario: str
    agg: int
    q_c: int
    d: int | None = None
    cycle_ns: float = P.CYCLE_NS
    tag: str = ""

    def config(self, n: int) -> Config:
        return Config(self.topology, self.link, self.scenario, self.agg, self.q_c, n, cycle_ns=self.cycle_ns,
                      d=self.d, tag=self.tag)

    @property
    def budgets(self) -> dict[str, float]:
        """The 1.1 us cycle and the 10 us reaction budget; the ms case is judged against its own cycle."""
        return P.BUDGETS_NS if self.cycle_ns == P.CYCLE_NS else {"cycle": self.cycle_ns}


def families() -> list[Family]:
    out = []
    for top, links in P.TOPOLOGY_LINKS.items():
        for ln in links:
            for agg in P.TOPOLOGY_AGGREGATION[top]:
                for sc in ["S1", "S2", "S3"]:
                    ds = [None] if sc != "S3" else P.S3_D_SWEEP.get((top, ln), [P.SCENARIOS["S3"]["d"]])
                    for d in ds:
                        for q_c in P.QUBITS_PER_CONTROLLER:
                            out.append(Family(top, ln, sc, agg, q_c, d))
    out.append(Family("T2", "L5-10G", "S1", 0, 64, cycle_ns=P.MS_CYCLE_NS, tag="Tc41.9ms"))
    return out


def bound_row(cfg: Config) -> dict:
    b = bound(cfg)
    steady, burst = cfg.frame_sizes()
    k = cfg.fan_in
    s3 = cfg.scenario == "S3"
    return dict(topology=cfg.topology, link=cfg.link, N=cfg.n, scenario=cfg.scenario_label,
                aggregation=cfg.agg, bound_ns=b["bound_ns"] if b["stable"] else math.nan,
                formula=formula(cfg), Q_c=cfg.q_c, Q_total=cfg.n * cfg.q_c,
                bound_steady_ns=b["bound_steady_ns"] if (s3 and b["stable"]) else None,
                bound_burst_ns=b["bound_burst_ns"] if (s3 and b["stable"]) else None,
                k=k, root_ports=math.ceil(cfg.n / k) if k else None,
                root_ports_exceed_published=(int(math.ceil(cfg.n / k) > P.ROOT_MAX_PORTS) if k else None),
                frame_bits=steady, burst_frame_bits=burst if s3 else None,
                cycle_ns=cfg.cycle_ns, utilisation=b["utilisation"], stable=b["stable"],
                switch_latency_assumed=int(cfg.link_spec.assumed), config_id=cfg.config_id)


def crossing_row(fam: Family, budget_name: str, budget_ns: float, extra: dict | None = None,
                 cycle_class: str = "all") -> dict:
    key = {"all": "bound_ns", "steady": "bound_steady_ns", "burst": "bound_burst_ns"}[cycle_class]
    n_cross, limit = crossing(fam.config, budget_ns, key=key)
    at = fam.config(max(n_cross or 1, 1))
    k_at = at.fan_in
    out = dict(topology=fam.topology, link=fam.link, scenario=fam.config(1).scenario_label,
               aggregation=fam.agg, Q_c=fam.q_c, cycle_class=cycle_class,
               budget=budget_name, budget_ns=budget_ns, N_cross=n_cross,
               Q_total_cross=n_cross * fam.q_c if n_cross is not None else None, limit=limit,
               k_at_cross=k_at, root_ports_at_cross=math.ceil(n_cross / k_at) if (k_at and n_cross) else None,
               aggregate_bps_at_cross=None, utilisation_at_cross=None, formula=formula(at))
    if n_cross:
        cfg = fam.config(n_cross)
        steady, _ = cfg.frame_sizes()
        out.update(aggregate_bps_at_cross=n_cross * steady / (cfg.cycle_ns * 1e-9),
                   utilisation_at_cross=bound(cfg)["utilisation"])
    if extra:
        out.update(extra)
    return out


def grid() -> tuple[pd.DataFrame, pd.DataFrame]:
    rows = []
    for top in P.GRID_TOPOLOGIES:
        for sc in P.GRID_SCENARIOS:
            for q_c in P.QUBITS_PER_CONTROLLER:
                for rate in P.GRID_RATES_GBPS:
                    for latency in P.GRID_LATENCIES_NS:
                        fam = Family(top, grid_link_name(rate, latency), sc, 0, q_c)
                        f_bits = fam.config(1).frame_sizes()[0]
                        for name, budget in P.BUDGETS_NS.items():
                            rows.append(crossing_row(fam, name, budget, dict(R_gbps=rate, L_ns=latency, frame_bits=f_bits)))
    cols = ["topology", "scenario", "Q_c", "R_gbps", "L_ns", "budget", "budget_ns", "N_cross", "Q_total_cross",
            "limit", "aggregate_bps_at_cross", "utilisation_at_cross", "frame_bits", "formula"]
    points = []
    for top, names in [("T2", ["L1", "L2", "L3", "L4", "L5-10G", "L5-100G", "L7"]), ("T4", ["L6-10G", "L6-100G"])]:
        for name in names:
            ln = LINKS[name]
            points.append(dict(topology=top, link=name, R_gbps=ln.rate_bps / 1e9, L_ns=ln.latency_ns,
                               assumed=int(ln.assumed), table_row=ln.row))
    return pd.DataFrame(rows)[cols], pd.DataFrame(points)


def saturation() -> pd.DataFrame:
    rows = []
    for t_c, f_bits, case in [(P.ANCHOR_CYCLE_NS, P.ANCHOR_FRAME_BITS, "anchor 1 (Sakata: 84 B every 500 ns)"),
                              (P.CYCLE_NS, P.ANCHOR_FRAME_BITS, "84 B every 1.1 us")]:
        for gbps, sakata in [(10, "saturates with eight FEUs"), (100, "saturates with about 80 FEUs")]:
            quotient = t_c * 1e-9 * gbps * 1e9 / f_bits
            first_saturated = math.floor(quotient) + 1   # smallest N with N F / R >= T_c (quotient not integer here)
            assert not quotient.is_integer()
            rows.append(dict(case=case, cycle_ns=t_c, frame_bits=f_bits, rate_gbps=gbps,
                             per_controller_gbps=f_bits / t_c, quotient_TcR_over_F=quotient,
                             largest_stable_N=first_saturated - 1, first_saturated_N=first_saturated,
                             sakata_statement=sakata if t_c == P.ANCHOR_CYCLE_NS else ""))
    return pd.DataFrame(rows)


def write_bounds(data: DataDir) -> None:
    data.bound.mkdir(parents=True, exist_ok=True)
    fams = families()
    rows = [bound_row(f.config(n)) for f in fams for n in P.N_VALUES]
    pd.DataFrame(rows).to_csv(data.bound / "bounds.csv", index=False)
    cross = [crossing_row(f, name, budget, cycle_class=cc) for f in fams for name, budget in f.budgets.items()
             for cc in (["steady", "burst"] if f.scenario == "S3" else ["all"])]
    pd.DataFrame(cross).to_csv(data.bound / "crossings.csv", index=False)
    g, points = grid()
    g.to_csv(data.bound / "grid.csv", index=False)
    points.to_csv(data.bound / "grid_points.csv", index=False)
    sat = saturation()
    sat.to_csv(data.bound / "saturation.csv", index=False)
    print(f"bounds: {len(rows)} rows, crossings: {len(cross)}, grid: {len(g)}")
    print(sat.to_string(index=False))
