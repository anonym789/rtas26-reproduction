"""One network configuration: topology, link, scenario, aggregation, Q_c and N."""
from __future__ import annotations

import zlib
from dataclasses import dataclass

from . import frames
from .links import Link, link as link_by_name
from .parameters import ANCHOR_FRAME_BITS, BASE_SEED, CYCLE_NS, SCENARIOS
from .topologies import TOPOLOGIES, Hop, Node, Topology


@dataclass(frozen=True)
class Config:
    topology: str
    link: str
    scenario: str                  # S1, S2 or S3
    agg: int                       # 1: the nodes merge the frames of a cycle
    q_c: int                       # physical qubits per controller
    n: int                         # controllers
    cycle_ns: float = CYCLE_NS
    d: int | None = None           # S3 burst period
    frame_bits: int | None = None  # fixed frame size (saturation anchor: 84 B)
    tag: str = ""                  # suffix of check configurations (cycle or frame overrides)

    @classmethod
    def from_id(cls, config_id: str, cycle_ns: float) -> Config:
        """Inverse of config_id; the cycle is not part of the id and comes from the raw file."""
        _, topology, link_name, scenario, agg, q_c, n = config_id.split("/")
        base, _, tag = scenario.partition("@")
        name, _, d = base.partition("-d")
        frame = ANCHOR_FRAME_BITS if tag.endswith("84B") else None
        return cls(topology, link_name, name, int(agg[3:]), int(q_c[2:]), int(n[1:]), cycle_ns=cycle_ns,
                   d=int(d) if d else None, frame_bits=frame, tag=tag)

    @property
    def scenario_label(self) -> str:
        s = self.scenario + (f"-d{self.d}" if self.scenario == "S3" else "")
        return s + (f"@{self.tag}" if self.tag else "")

    @property
    def config_id(self) -> str:
        return f"net/{self.topology}/{self.link}/{self.scenario_label}/agg{self.agg}/Qc{self.q_c}/N{self.n}"

    @property
    def file_stem(self) -> str:
        return f"{self.topology}_{self.link}_{self.scenario_label}_agg{self.agg}_Qc{self.q_c}_N{self.n}"

    @property
    def seed(self) -> int:
        return BASE_SEED + zlib.crc32(self.config_id.encode()) % 1_000_000

    @property
    def link_spec(self) -> Link:
        return link_by_name(self.link)

    @property
    def topology_spec(self) -> Topology:
        return TOPOLOGIES[self.topology]

    @property
    def path(self) -> list[Hop | Node]:
        return self.topology_spec.path(self.link_spec, self.n, bool(self.agg))

    @property
    def fan_in(self) -> int | None:
        return self.topology_spec.fan_in(self.n)

    @property
    def frames_at_decoder(self) -> int:
        return self.topology_spec.frames_at_decoder(self.n, bool(self.agg))

    def frame_sizes(self, merge: int = 1) -> tuple[int, int]:
        """(steady-cycle, burst-cycle) bits of a frame that carries the outcomes of `merge` controllers
        (1 = one controller's frame; more = a merged frame with one header for all)."""
        if self.frame_bits is not None:
            return self.frame_bits, self.frame_bits
        b = SCENARIOS[self.scenario]["b"]
        framing = self.link_spec.framing
        steady = frames.frame_bits(frames.payload_bits(merge * frames.outcomes(self.q_c, False), b), framing)
        burst = frames.frame_bits(frames.payload_bits(merge * frames.outcomes(self.q_c, True), b), framing)
        return steady, burst

    def is_burst(self, cycle: int) -> bool:
        return self.scenario == "S3" and cycle % self.d == 0
