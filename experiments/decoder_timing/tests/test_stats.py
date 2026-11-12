import numpy as np
import pytest

from qecdec.stats import gpd_fit, pwcet_rows, timing_stats


def test_timing_stats():
    t = np.arange(1, 1001, dtype=float)
    s = timing_stats(t, rounds=10)
    assert s["mean_ns"] == pytest.approx(500.5)
    assert s["median_ns"] == pytest.approx(500.5)
    assert s["max_ns"] == 1000 and s["min_ns"] == 1
    assert s["p999_ns"] == pytest.approx(np.quantile(t, 0.999))
    assert s["mean_per_round_ns"] == pytest.approx(50.05)


def test_gpd_fit_recovers_an_exponential_tail():
    rng = np.random.default_rng(1)
    t = 1000 + rng.exponential(100, size=200_000)
    f = gpd_fit(t, float(np.quantile(t, 0.9)))
    assert abs(f["shape_xi"]) < 0.05          # exponential tail: xi = 0
    assert f["scale"] == pytest.approx(100, rel=0.05)
    assert f["q_1e-6_ns"] == pytest.approx(1000 + 100 * np.log(1e6), rel=0.02)   # P(T > x) = 1e-6


def test_gpd_fit_needs_enough_exceedances():
    assert gpd_fit(np.arange(100, dtype=float), 95.0) is None


def test_pwcet_fit_of_the_post_processor_mode():
    rng = np.random.default_rng(2)
    n = 100_000
    osd = (rng.random(n) < 0.2).astype(int)
    t = np.where(osd == 1, 5000 + rng.exponential(500, n), 1000 + rng.exponential(50, n))
    main, stability = pwcet_rows(dict(decoder="bposd", basis="first"), t, rounds=5, osd=osd)
    assert len(stability) == 5
    assert main["fit_ok"] == 1
    assert main["exceedance_fraction"] == pytest.approx(0.1 * osd.mean(), rel=0.01)
    assert "OSD-triggered" in main["note"]
