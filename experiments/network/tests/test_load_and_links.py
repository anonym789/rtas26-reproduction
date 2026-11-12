import pytest

from qecnet import frames
from qecnet.links import LINKS, grid_link_name, link


def test_ethernet_minimum_frame_holds_up_to():
    assert frames.ethernet_floor() == {"b1_outcomes": 304, "b4_outcomes": 76, "burst_b1_q": 152}


@pytest.mark.parametrize("q_c, b, burst, ethernet_bytes, custom_bits", [
    (64, 1, False, 84, 96),     # 32 outcomes + 8 B header
    (64, 1, True, 84, 128),     # the burst adds the data qubits
    (256, 4, False, 110, 576),  # the only Ethernet frame above the 84 B minimum
])
def test_frame_sizes(q_c, b, burst, ethernet_bytes, custom_bits):
    payload = frames.payload_bits(frames.outcomes(q_c, burst), b)
    assert frames.frame_bits(payload, "ethernet") == 8 * ethernet_bytes
    assert frames.frame_bits(payload, "custom") == custom_bits


def test_line_coding_and_latency_accounting():
    assert LINKS["L3"].payload_rate_bps == pytest.approx(10e9 * 64 / 66)
    assert LINKS["L1"].payload_rate_bps == 12.5e9
    lo, hi, sym = LINKS["L4"].hop_latency()   # the 361.6 ns figure contains one 84 B frame
    assert (lo, hi, sym) == (pytest.approx(361.6 - 67.2), pytest.approx(361.6 - 67.2), "L_eff")
    assert LINKS["L3"].hop_latency() == (141.0, 173.0, "L")


def test_grid_links():
    name = grid_link_name(25, 200)
    assert name == "G25G-200ns"
    ln = link(name)
    assert (ln.rate_bps, ln.latency_ns, ln.framing, ln.element) == (25e9, 200.0, "ethernet", "node")
    with pytest.raises(KeyError):
        link("L9")
