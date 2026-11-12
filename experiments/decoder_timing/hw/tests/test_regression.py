"""The code reproduces the recorded campaign of paths.data (the comparisons are skipped without the data)."""
import dataclasses
import gzip

import pandas as pd
import pytest

from qechw.check import compare_index
from qechw.config import Run, load
from qechw.data import DataDir
from qechw.microblossom.calibrate import calibrate
from qechw.microblossom.logs import collect
from qechw.transfer import transfer

CFG = load()
RECORDED = DataDir(CFG.data, CFG.data, CFG.literature)   # the record holds raw/, level2/, stats/ like an output folder
needs_record = pytest.mark.skipif(not RECORDED.stats.exists(), reason="recorded hardware data not present")


@needs_record
def test_syndrome_index(bb_syndromes):
    assert compare_index(bb_syndromes / "index.csv", RECORDED.syndromes / "index.csv") == (True, "1 of 2 rows, all as recorded")


def test_transfer_counters(tmp_path, bb_syndromes):
    data = DataDir(tmp_path, tmp_path, CFG.literature)
    (tmp_path / "syndromes").symlink_to(bb_syndromes)
    settings = dataclasses.replace(CFG.transfer, workers=1)
    transfer(data, CFG.relay, settings, Run("relaybp1", 6, 0.001, shots=2000))   # one chunk: same seeds as the record
    name = "fpga_transfer_relaybp1_bb_d6_p0.001.csv.gz"
    counts = lambda df: df[~df.counter_name.str.startswith("cpu_wall")].reset_index(drop=True)
    new = pd.read_csv(tmp_path / "raw" / name, dtype=str)
    window = new[new.counter_name == "iterations_window"]   # time_ns repeats on every counter row of a shot
    iterations = window.counter_value.astype(int)
    assert len(window) == 2000 and iterations.between(1, CFG.relay.max_iterations).all()
    assert (window.time_ns.astype(float) == CFG.relay.ns_per_iteration * iterations).all()
    if RECORDED.raw.exists():
        old = pd.read_csv(RECORDED.raw / name, dtype=str)
        pd.testing.assert_frame_equal(counts(new), counts(old[old.shot.astype(int) < 2000]))


@needs_record
def test_micro_blossom_collection_and_calibration(tmp_path):
    data = DataDir(tmp_path, CFG.data, CFG.literature)
    mb = CFG.microblossom
    for s in mb.collect:
        assert collect(data.campaign_level2, data.level2, s, mb.freq_hz[s.d]) is not None, s
    calibrate(data, mb)
    for name in ("level2_batch_correction.csv", "level2_batch_validation.csv"):
        assert (data.stats / name).read_bytes() == (RECORDED.stats / name).read_bytes(), name
    for d in (9, 13):   # S1's and F3's input
        name = f"fpga_sim_microblossombatch_surface_d{d}_p0.001.csv.gz"
        assert gzip.decompress((data.raw / name).read_bytes()) == gzip.decompress((RECORDED.raw / name).read_bytes()), name
