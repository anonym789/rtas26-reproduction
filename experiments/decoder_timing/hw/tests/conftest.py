import pytest

from qechw.syndromes import write_syndromes


@pytest.fixture(scope="session")
def bb_syndromes(tmp_path_factory):
    """The bivariate-bicycle syndromes at d = 6, p = 1e-3 (the CPU experiment's seed), generated once per test run."""
    out = tmp_path_factory.mktemp("syndromes")
    write_syndromes(out, "bb", [6], [0.001], [0.001], 100_000)
    return out
