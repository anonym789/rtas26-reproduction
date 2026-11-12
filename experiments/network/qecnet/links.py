"""The links of the paper's network table (literature table network_links.csv), and the synthetic links of the
R x L grid."""
from __future__ import annotations

import csv
from dataclasses import dataclass

from .parameters import LITERATURE

CODING_FACTOR = {None: 1.0, "64b66b": 64 / 66}


@dataclass(frozen=True)
class Link:
    """One link technology.

    element says where the latency figure was measured and is therefore charged: "link" on every
    link hop (FPGA-to-FPGA links), "node" once per traversal of the aggregator or switch, whose edge
    links then cost serialisation only. includes_ser_bits: the figure already contains the
    serialisation of a frame of this size.
    """
    rate_bps: float                     # line rate as in the table row
    latency_ns: float
    framing: str                        # "ethernet" or "custom"
    element: str                        # "link" or "node"
    coding: str | None = None           # "64b66b" where the source states 64B/66B line coding
    latency_range_ns: tuple[float, float] | None = None   # uniform latency (L3 only)
    includes_ser_bits: int = 0
    assumed: bool = False
    row: str = ""                       # the table row the figures come from

    @property
    def payload_rate_bps(self) -> float:
        """Rate at which frame bits are serialised: the line rate after line coding."""
        return self.rate_bps * CODING_FACTOR[self.coding]

    @property
    def has_jitter(self) -> bool:
        return self.latency_range_ns is not None

    def hop_latency(self) -> tuple[float, float, str]:
        """(lowest, highest, formula symbol) latency of one link hop, net of any serialisation the
        figure already contains."""
        lo, hi = self.latency_range_ns or (self.latency_ns, self.latency_ns)
        included = self.includes_ser_bits / self.payload_rate_bps * 1e9
        return lo - included, hi - included, ("L_eff" if included else "L")


def read_links(path) -> dict[str, Link]:
    """The link table: one row per link with its source (the table row of the paper or the assumption)."""
    with open(path, newline="") as f:
        return {r["link"]: Link(float(r["rate_bps"]), float(r["latency_ns"]), r["framing"], r["element"],
                                coding=r["coding"] or None,
                                latency_range_ns=(float(r["latency_low_ns"]), float(r["latency_high_ns"]))
                                if r["latency_low_ns"] else None,
                                includes_ser_bits=int(r["includes_ser_bits"]), assumed=r["assumed"] == "true",
                                row=r["source"])
                for r in csv.DictReader(f)}


LINKS = read_links(LITERATURE / "network_links.csv")


def grid_link_name(rate_gbps: float, latency_ns: float) -> str:
    return f"G{rate_gbps:g}G-{latency_ns:g}ns"


def link(name: str) -> Link:
    """A table link by name, or a node-type Ethernet link of the R x L grid ("G10G-100ns")."""
    if name in LINKS:
        return LINKS[name]
    if name.startswith("G"):
        rate, latency = name[1:].split("G-")
        return Link(float(rate) * 1e9, float(latency.removesuffix("ns")), "ethernet", "node", row="R x L grid cell")
    raise KeyError(name)
