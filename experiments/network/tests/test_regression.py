"""The code regenerates the recorded tables of paths.data byte for byte (skipped without the data)."""

import numpy as np
import pandas as pd
import pytest

from qecnet import simulation
from qecnet.bounds import write_bounds
from qecnet.configuration import Config
from qecnet import parameters as P
from qecnet.data import DataDir
from qecnet.frames import frame_size_table
from qecnet.jobs import cycles

RECORDED = DataDir(P.DATA, P.DATA / "sim" / "raw")
pytestmark = pytest.mark.skipif(not RECORDED.bound.exists(), reason="recorded network data not present")


def test_load_table(tmp_path):
    out = tmp_path / "frame_sizes.csv"
    frame_size_table().to_csv(out, index=False)
    assert out.read_bytes() == (RECORDED.load / "frame_sizes.csv").read_bytes()


def test_bound_tables(tmp_path):
    write_bounds(DataDir(tmp_path, RECORDED.runs))
    for name in ["bounds.csv", "crossings.csv", "grid.csv", "grid_points.csv", "saturation.csv"]:
        assert (tmp_path / "bound" / name).read_bytes() == (RECORDED.bound / name).read_bytes(), name


@pytest.mark.parametrize("config_id", [
    "net/T1/L3/S1@single-hop/agg0/Qc64/N1",   # random latency, 10^5 cycles
    "net/T2/L5-10G/S3-d13/agg1/Qc64/N128",
])
def test_simulation_reproduces_the_stored_run(config_id):
    sub = "checks" if "@" in config_id else ""
    cfg = Config.from_id(config_id, 1100.0)
    stored = pd.read_csv(RECORDED.runs_folder(sub) / f"{cfg.file_stem}.csv.gz")
    res = simulation.run(cfg, *cycles(cfg))
    again = np.array([float("%.6f" % v) for v in res["per_cycle"]["round_completion_ns"]])
    assert np.array_equal(again, stored["round_completion_ns"].to_numpy())
