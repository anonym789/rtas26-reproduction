import csv

import numpy as np
import pytest

from qecdec import parameters as P
from qecdec.data import DataDir
from qecdec.grid import GridPoint, all_jobs, max_seconds_per_rep
from qecdec.syndromes import generate, load_b8, read_index, update_index

RECORDED = DataDir(P.DATA, P.DATA)


def test_grid_point():
    pt = GridPoint("surface", 13, 0.001)
    assert pt.name == "surface_d13_p0.001"
    assert (pt.rounds, pt.shots, pt.reps, pt.seed) == (13, 100_000, 3, 113001)
    assert GridPoint("surface", 25, 0.005).shots == 20_000
    assert GridPoint("bb", 12, 0.003).reps == 1
    assert GridPoint("color", 9, 0.003).seed == 209002


def test_campaign_jobs():
    jobs = list(all_jobs())
    assert len(jobs) == 135   # 128 raw files plus the 7 BP+OSD grid points skipped by the 1 s rule
    assert ("bposd", GridPoint("surface", 17, 0.001)) not in jobs   # BP+OSD only up to d = 15
    assert max_seconds_per_rep("bposd", "bb") == 12 * 3600


def test_syndromes_are_deterministic_and_match_the_record(tmp_path):
    pt = GridPoint("surface", 3, 0.003)
    a = generate(pt, tmp_path / "a")
    b = generate(pt, tmp_path / "b")
    assert a == b
    assert (tmp_path / "a" / f"{pt.name}.dets.b8").read_bytes() == (tmp_path / "b" / f"{pt.name}.dets.b8").read_bytes()
    dets = load_b8(tmp_path / "a" / f"{pt.name}.dets.b8", a["num_detectors"])
    assert dets.shape == (pt.shots, a["num_detectors"])
    assert np.array_equal(dets.sum(axis=1), np.load(tmp_path / "a" / f"{pt.name}.ndet.npy"))
    update_index(tmp_path / "a", [a])
    if (RECORDED.syndromes / "index.csv").exists():
        with open(tmp_path / "a" / "index.csv") as f:
            row = next(csv.DictReader(f))
        assert row == read_index(RECORDED.syndromes, pt)


def test_seed_offset_changes_the_sample(tmp_path):
    pt = GridPoint("surface", 3, 0.003)
    generate(pt, tmp_path / "a")
    generate(pt, tmp_path / "b", seed_offset=7919)
    assert (tmp_path / "a" / f"{pt.name}.dets.b8").read_bytes() != (tmp_path / "b" / f"{pt.name}.dets.b8").read_bytes()


def test_missing_grid_point_is_reported(tmp_path):
    update_index(tmp_path, [generate(GridPoint("surface", 3, 0.001), tmp_path)])
    with pytest.raises(SystemExit):
        read_index(tmp_path, GridPoint("surface", 5, 0.001))
