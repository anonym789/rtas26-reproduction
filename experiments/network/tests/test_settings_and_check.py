"""Settings and literature tables as the modules see them, and the comparison with the recorded tables."""
from qecnet import parameters as P
from qecnet.check import compare
from qecnet.links import LINKS


def test_sourced_constants_keep_their_types():
    assert (P.CYCLE_NS, P.MS_CYCLE_NS, P.BUDGETS_NS) == (1100.0, 41.9e6, {"cycle": 1100.0, "reaction": 10_000.0})
    assert all(isinstance(v, int) for v in (P.HEADER_BITS, P.ETH_OVERHEAD_BITS, P.ETH_MIN_WIRE_BITS, P.PORT_CAP_K))
    assert isinstance(P.AGGREGATION_DELAY_NS, float) and P.ANCHOR_FRAME_BITS == 84 * 8
    assert P.QUBITS_PER_CONTROLLER == [16, 64, 256] and P.BITS_PER_OUTCOME == [1, 4]


def test_run_settings():
    assert list(P.TOPOLOGY_LINKS) == ["T1", "T2", "T3", "T3-k7", "T4"]
    assert P.SCENARIOS == {"S1": dict(b=1, d=None), "S2": dict(b=4, d=None), "S3": dict(b=1, d=13)}
    assert P.S3_D_SWEEP == {("T2", "L5-10G"): [5, 13, 25], ("T3", "L2"): [5, 13, 25]}
    assert P.GRID_DIAGONAL[0] == (1, 50) and P.BASE_SEED == 20261020
    assert all(link in LINKS for links in P.TOPOLOGY_LINKS.values() for link in links)


def test_link_table():
    assert LINKS["L4"].includes_ser_bits == P.ETH_MIN_WIRE_BITS
    assert LINKS["L3"].latency_range_ns == (141.0, 173.0) and LINKS["L3"].coding == "64b66b"
    assert LINKS["L6-10G"].assumed and not LINKS["L1"].assumed and LINKS["L1"].coding is None


def test_compare(tmp_path):
    recorded, new = tmp_path / "rec.csv", tmp_path / "new.csv"
    recorded.write_text("id,x\na,1\n")
    assert compare(new, recorded) == (False, "missing in the output")
    new.write_text("id,x\na,1\n")
    assert compare(new, recorded) == (True, "identical")
    new.write_text("id,x\na,2\n")
    assert compare(new, recorded) == (False, "differs")
