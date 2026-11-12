"""Load model: the bits one controller sends per cycle, and the frame they occupy on a link."""
from __future__ import annotations

import pandas as pd

from . import parameters as P
from .links import LINKS

FRAMING_SOURCE = {
    "ethernet": "frame = max(84 B, payload + 38 B) on the wire (IEEE 802.3 minimum frame; Sakata); 8 B header assumed (E3.md; Sakata's SFF has 14 B)",
    "custom": "frame = payload incl. 8 B header (custom serial; header size assumed in E3.md, no source)",
}


def outcomes(qubits_per_controller: int, burst: bool) -> int:
    """Measurement outcomes per controller and cycle: the q = Q_c / 2 ancillas, and in a burst cycle
    the data qubits as well."""
    q = qubits_per_controller // 2
    return 2 * q if burst else q


def payload_bits(n_outcomes: int, bits_per_outcome: int) -> int:
    return n_outcomes * bits_per_outcome + P.HEADER_BITS


def frame_bits(payload: int, framing: str) -> int:
    """Bits one frame occupies on the link."""
    if framing == "ethernet":
        return max(P.ETH_MIN_WIRE_BITS, payload + P.ETH_OVERHEAD_BITS)
    if framing == "custom":
        return payload
    raise ValueError(framing)


def ethernet_floor() -> dict[str, int]:
    """Largest outcome counts per frame that still fit the 84 B Ethernet minimum frame."""
    room = P.ETH_MIN_WIRE_BITS - P.ETH_OVERHEAD_BITS - P.HEADER_BITS
    return {"b1_outcomes": room // 1, "b4_outcomes": room // 4, "burst_b1_q": room // 2}


def frame_size_table() -> pd.DataFrame:
    """One row per (Q_c, b, burst, link): payload, frame and the per-controller rate at the 1.1 us cycle."""
    rows = []
    for q_c in P.QUBITS_PER_CONTROLLER:
        for b in P.BITS_PER_OUTCOME:
            for burst in (0, 1):
                n_out = outcomes(q_c, burst)
                payload = payload_bits(n_out, b)
                for name, ln in LINKS.items():
                    bits = frame_bits(payload, ln.framing)
                    source = (f"Q_c: {P.QUBITS_PER_CONTROLLER_SOURCE[q_c]}; q = Q_c/2 (paper QEC sec.); "
                              f"b: {P.BITS_PER_OUTCOME_SOURCE[b]}; "
                              + ("burst adds q data-qubit outcomes (S3); " if burst else "")
                              + FRAMING_SOURCE[ln.framing])
                    rows.append({"Q_c": q_c, "q": q_c // 2, "b": b, "burst": burst, "link": name,
                                 "payload_bits": payload, "frame_bits": bits,
                                 "rate_bps_at_1.1us": bits / (P.CYCLE_NS * 1e-9), "source": source,
                                 "outcomes": n_out, "framing": ln.framing, "line_rate_bps": ln.rate_bps,
                                 "link_rate_bps": ln.payload_rate_bps,
                                 "serialisation_ns": bits / ln.payload_rate_bps * 1e9})
    return pd.DataFrame(rows)
