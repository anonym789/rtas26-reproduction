import numpy as np
import pytest

from qecnet import simulation
from qecnet.calculus import bound
from qecnet.configuration import Config


@pytest.mark.parametrize("cfg", [
    Config("T1", "L4", "S1", 0, 64, 4),
    Config("T2", "L5-10G", "S1", 0, 64, 8),
    Config("T2", "L5-10G", "S1", 1, 64, 300),
    Config("T3", "L2", "S1", 1, 64, 100),
    Config("T3", "L2", "S3", 0, 64, 64, d=5),
])
def test_fixed_latencies_reach_the_bound_exactly(cfg):
    res = simulation.run(cfg, warmup=10, recorded=40)
    rc = res["per_cycle"]["round_completion_ns"]
    assert not np.isnan(rc).any()
    assert rc.max() == pytest.approx(bound(cfg)["bound_ns"], rel=1e-12)


def test_random_latency_stays_below_the_bound():
    cfg = Config("T3", "L3", "S1", 0, 64, 16)
    rc = simulation.run(cfg, warmup=10, recorded=2000)["per_cycle"]["round_completion_ns"]
    assert rc.max() <= bound(cfg)["bound_ns"]
    assert rc.min() < rc.max()


def test_same_seed_same_result():
    cfg = Config("T3", "L3", "S1", 0, 64, 16)
    a = simulation.run(cfg, warmup=10, recorded=200)["per_cycle"]["round_completion_ns"]
    b = simulation.run(cfg, warmup=10, recorded=200)["per_cycle"]["round_completion_ns"]
    assert np.array_equal(a, b)


def test_overloaded_port_is_unstable():
    res = simulation.run(Config("T2", "L5-10G", "S1", 0, 64, 32), warmup=10, recorded=40)
    assert max(p["offered_load"] for p in res["ports"]) >= 1
    rc = res["per_cycle"]["round_completion_ns"]
    assert np.all(np.diff(rc) > 0)   # the queue grows every cycle
