"""The code reproduces the recorded campaign of paths.data (skipped without the data)."""
import shutil

import pandas as pd
import pytest

from qecdec import parameters as P
from qecdec.data import DataDir
from qecdec.grid import GridPoint
from qecdec.measure import measure
from qecdec.stats import write_stats
from qecdec.syndromes import generate, update_index

RECORDED = DataDir(P.DATA, P.DATA)   # the record holds raw/, syndromes/index.csv and stats/ like an output folder
pytestmark = pytest.mark.skipif(not (RECORDED.raw / "runs.csv").exists(), reason="recorded decoder data not present")

# columns of a raw file that do not depend on timing
DETERMINISTIC = ["decoder", "code", "d", "p", "rounds", "shot", "rep", "n_detections", "logical_error",
                 "logical_flips", "bp_iterations", "osd_triggered", "timing_method"]


@pytest.mark.parametrize("decoder, point", [
    ("bposd", GridPoint("surface", 3, 0.003)),
    ("bposd", GridPoint("color", 3, 0.001)),
])
def test_measurement_reproduces_the_decoder_output(tmp_path, decoder, point):
    data = DataDir(tmp_path, tmp_path)
    update_index(data.syndromes, [generate(point, data.syndromes)])
    # 1,000 shots: the warm-up then ends on the same shot as in the recorded run, which matters because ldpc
    # leaves its iteration count unchanged for an empty syndrome (such shots repeat the previous count)
    measure(data, decoder, point, reps=1, shots=1000)
    new = pd.read_csv(data.raw_file(decoder, point))
    old = pd.read_csv(RECORDED.raw_file(decoder, point))
    old = old[(old.rep == 1) & (old.shot < 1000)].reset_index(drop=True)
    pd.testing.assert_frame_equal(new[DETERMINISTIC], old[DETERMINISTIC])


def test_statistics_reproduce_the_recorded_rows(tmp_path):
    data = DataDir(tmp_path / "out", tmp_path)   # the statistics read the campaign in tmp_path
    (tmp_path / "raw").mkdir()
    (tmp_path / "syndromes").mkdir()
    names = ["pymatching_surface_d3_p0.001", "bposd_surface_d3_p0.003"]
    for name in names:
        (data.campaign_raw / f"{name}.csv.gz").symlink_to(RECORDED.raw / f"{name}.csv.gz")
    shutil.copy(RECORDED.syndromes / "index.csv", data.campaign_index)
    write_stats(data)
    new = pd.read_csv(data.stats / "summary.csv", dtype=str)
    old = pd.read_csv(RECORDED.stats / "summary.csv", dtype=str)
    keys = new[["decoder", "code", "d", "p"]].drop_duplicates()
    old = old.merge(keys, on=["decoder", "code", "d", "p"])
    pd.testing.assert_frame_equal(new.reset_index(drop=True), old.reset_index(drop=True))
