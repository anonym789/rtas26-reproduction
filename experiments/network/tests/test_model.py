import math

import pytest

from qecnet.calculus import bound, crossing, formula
from qecnet.configuration import Config
from qecnet.parameters import ANCHOR_FRAME_BITS, MS_CYCLE_NS

F_ETH_10G = 84 * 8 / 10e9 * 1e9   # 67.2 ns: one minimum Ethernet frame at 10 Gb/s


@pytest.mark.parametrize("cfg", [
    Config("T2", "L5-10G", "S1", 1, 64, 300),
    Config("T3-k7", "L3", "S3", 0, 16, 1000, d=5),
    Config("T2", "L5-10G", "S1", 0, 64, 8, cycle_ns=MS_CYCLE_NS, tag="Tc41.9ms"),
    Config("T4", "L6-100G", "S1", 0, 64, 75, cycle_ns=500.0, frame_bits=ANCHOR_FRAME_BITS, tag="Tc500-84B"),
])
def test_config_id_round_trip(cfg):
    assert Config.from_id(cfg.config_id, cfg.cycle_ns) == cfg


def test_seed_is_derived_from_the_id():
    assert Config("T3", "L3", "S1", 0, 64, 8).seed == 20404017   # as recorded in the raw file


def test_direct_link_with_the_frame_in_the_figure():
    assert bound(Config("T1", "L4", "S1", 0, 64, 1000))["bound_ns"] == pytest.approx(361.6)


@pytest.mark.parametrize("n", [1, 8, 16])
def test_star_is_ingress_plus_node_plus_contended_port(n):
    b = bound(Config("T2", "L5-10G", "S1", 0, 64, n))
    assert b["stable"] == 1
    assert b["bound_ns"] == pytest.approx(F_ETH_10G + 450 + n * F_ETH_10G)


def test_star_saturates_when_the_port_is_full():
    b = bound(Config("T2", "L5-10G", "S1", 0, 64, 17))   # 17 x 67.2 ns > 1.1 us
    assert b["stable"] == 0 and math.isinf(b["bound_ns"]) and b["utilisation"] >= 1


@pytest.mark.parametrize("topology, link, agg, budget, expected", [
    ("T2", "L5-10G", 0, 1100, (8, "latency")),
    ("T2", "L5-10G", 0, 10_000, (16, "throughput")),
    ("T2", "L5-10G", 1, 1100, (170, "latency")),
    ("T3", "L3", 0, 1100, (5625, "latency")),
    ("T4", "L6-10G", 0, 1100, (9, "latency")),
])
def test_crossings_quoted_in_the_readme(topology, link, agg, budget, expected):
    assert crossing(lambda n: Config(topology, link, "S1", agg, 64, n), budget) == expected


def test_never_crosses_without_contention():
    assert crossing(lambda n: Config("T1", "L2", "S1", 0, 64, n), 1100) == (None, "none")


def test_tree_fan_in_and_frames_at_the_decoder():
    balanced = Config("T3", "L2", "S1", 1, 64, 16000)
    assert balanced.fan_in == 127 and balanced.frames_at_decoder == 126
    capped = Config("T3-k7", "L2", "S1", 0, 64, 16000)
    assert capped.fan_in == 7 and capped.frames_at_decoder == 16000
    assert Config("T2", "L5-10G", "S1", 1, 64, 300).frames_at_decoder == 1
    assert Config("T2", "L5-10G", "S1", 0, 64, 300).fan_in is None


def test_merged_frame_carries_every_outcome():
    cfg = Config("T2", "L5-10G", "S1", 1, 64, 300)
    assert cfg.frame_sizes(merge=300)[0] == 300 * 32 + 64 + 38 * 8


def test_formula():
    assert formula(Config("T2", "L5-10G", "S1", 0, 64, 8)).startswith("F/R + L + N*F/R")
    assert "k = min(N, 7)" in formula(Config("T3-k7", "L3", "S1", 0, 64, 8))
