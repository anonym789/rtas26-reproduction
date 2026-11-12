"""How N controllers reach the decoder.

A topology turns a link and a number of controllers into a path: the stages a frame passes from a
controller to the decoder. The network-calculus bound and the simulation are both built from this
path, so they model the same network.

  Hop   one FIFO output port carrying `flows` frames per cycle: serialisation F / R, then the hop
        latency (uniform on [lat_lo, lat_hi] for L3, fixed otherwise)
  Node  an aggregator, switch or leaf: a fixed processing delay; with aggregate=True it merges the
        frames of one cycle into one frame that carries the outcomes of all its children
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Callable

from .links import Link
from .parameters import AGGREGATION_DELAY_NS, PORT_CAP_K


@dataclass(frozen=True)
class Hop:
    flows: int        # frames per cycle through this port
    lat_lo: float     # ns
    lat_hi: float     # ns
    rate: float       # bit/s used for serialisation
    flows_sym: str    # "1", "N" or "k" in the formula
    lat_sym: str      # "L", "L_eff" or "" in the formula
    merge: int = 1    # controllers whose outcomes each frame on this hop carries (after aggregation)
    merge_sym: str = ""


@dataclass(frozen=True)
class Node:
    delay: float      # ns
    aggregate: bool
    delay_sym: str    # "L", "P" or "" in the formula


class Topology:
    """Controllers are served in groups by one node each; the node's output port feeds the decoder."""
    name: str
    node_role: str = ""      # name of the node's output port in the simulation
    group_symbol: str = ""   # "N" or "k" in the formula

    def group(self, n: int) -> int:
        """Controllers per node."""
        raise NotImplementedError

    def fan_in(self, n: int) -> int | None:
        """Controllers per leaf, for trees only."""
        return None

    def rule(self) -> str:
        """How the group size is chosen, for the formula."""
        return ""

    def frames_at_decoder(self, n: int, aggregate: bool) -> int:
        """Frames of one cycle the decoder waits for: one per controller, or one per node when the
        nodes aggregate."""
        return math.ceil(n / self.group(n)) if aggregate else n

    def path(self, ln: Link, n: int, aggregate: bool) -> list[Hop | Node]:
        raise NotImplementedError

    def _through_node(self, ln: Link, n: int, aggregate: bool) -> list[Hop | Node]:
        """Controller link (serialisation only), the node with the measured latency, the node's output
        port carrying either every frame of its group or one merged frame."""
        rate = ln.payload_rate_bps
        g = self.group(n)
        return [Hop(1, 0.0, 0.0, rate, "1", ""),
                Node(ln.latency_ns, aggregate, "L"),
                self._output(g, 0.0, 0.0, rate, "", aggregate)]

    def _output(self, g: int, lo: float, hi: float, rate: float, lat_sym: str, aggregate: bool) -> Hop:
        if aggregate:
            return Hop(1, lo, hi, rate, "1", lat_sym, merge=g, merge_sym=self.group_symbol)
        return Hop(g, lo, hi, rate, self.group_symbol, lat_sym)


@dataclass(frozen=True)
class Direct(Topology):
    """One link per controller into the decoder FPGA, no contention."""
    name: str

    def group(self, n: int) -> int:
        return 1

    def path(self, ln: Link, n: int, aggregate: bool) -> list[Hop | Node]:
        assert ln.element == "link" and not aggregate
        lo, hi, lat_sym = ln.hop_latency()
        return [Hop(1, lo, hi, ln.payload_rate_bps, "1", lat_sym)]


@dataclass(frozen=True)
class Star(Topology):
    """Every controller into one aggregator or switch, which has one output port into the decoder."""
    name: str
    can_aggregate: bool
    node_role: str = ""
    group_symbol: str = "N"

    def group(self, n: int) -> int:
        return n

    def path(self, ln: Link, n: int, aggregate: bool) -> list[Hop | Node]:
        assert ln.element == "node" and (self.can_aggregate or not aggregate)
        return self._through_node(ln, n, aggregate)


@dataclass(frozen=True)
class Tree(Topology):
    """Two levels: leaves of k controllers, each with one uplink into the root that hosts the decoder."""
    name: str
    k: Callable[[int], int]
    rule_text: str
    node_role: str = "leaf uplink"
    group_symbol: str = "k"

    def group(self, n: int) -> int:
        return self.k(n)

    def fan_in(self, n: int) -> int | None:
        return self.k(n)

    def rule(self) -> str:
        return self.rule_text

    def path(self, ln: Link, n: int, aggregate: bool) -> list[Hop | Node]:
        if ln.element == "node":
            return self._through_node(ln, n, aggregate)
        # custom links: both hops carry the link latency; an aggregating leaf adds the aggregator's processing
        lo, hi, lat_sym = ln.hop_latency()
        rate = ln.payload_rate_bps
        leaf = Node(AGGREGATION_DELAY_NS, True, "P") if aggregate else Node(0.0, False, "")
        return [Hop(1, lo, hi, rate, "1", lat_sym), leaf, self._output(self.group(n), lo, hi, rate, lat_sym, aggregate)]


TOPOLOGIES: dict[str, Topology] = {
    "T1": Direct("T1"),
    "T2": Star("T2", node_role="aggregator uplink", can_aggregate=True),
    "T3": Tree("T3", k=lambda n: math.ceil(math.sqrt(n)), rule_text="k = ceil(sqrt(N))"),
    "T3-k7": Tree("T3-k7", k=lambda n: min(n, PORT_CAP_K), rule_text=f"k = min(N, {PORT_CAP_K})"),
    "T4": Star("T4", node_role="switch output port", can_aggregate=False),
}
