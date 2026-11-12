"""The GPU harness with a stand-in decoder (no GPU needed): files, counters and logical errors."""
import dataclasses

import pandas as pd

import fake_cudaq_qec
from qechw.config import Run, load
from qechw.data import RAW_COLUMNS, DataDir
from qechw.gpu import measure

CFG = load()


def test_measure_with_a_stand_in_decoder(tmp_path, bb_syndromes):
    data = DataDir(tmp_path, tmp_path, CFG.literature)
    (tmp_path / "raw").mkdir()
    (tmp_path / "syndromes").symlink_to(bb_syndromes)
    settings = dataclasses.replace(CFG.gpu, reps=2, warmup=10, cupti_shots=10, batch_shots=32, batch_sizes=[1, 16])
    measure(data, CFG.relay, settings, Run("relaybp1", 6, 0.001, shots=50), qec=fake_cudaq_qec)
    raw = pd.read_csv(tmp_path / "raw" / "gpu_measured_relaybp1_bb_d6_p0.001.csv.gz")
    assert list(raw.columns) == RAW_COLUMNS
    assert len(raw) == 2 * 50 * 7                       # passes x shots x counters
    it = raw[raw.counter_name == "iterations_window"]
    assert it.counter_value.between(1, 7).all()        # the stand-in decoder reports 1..7 iterations
    host = raw.pivot_table(index=["rep", "shot"], columns="counter_name", values="counter_value")
    times = raw.drop_duplicates(["rep", "shot"]).set_index(["rep", "shot"]).time_ns
    assert (times == host.host_ns_x + host.host_ns_z).all()   # the two decoders run one after the other
    batch = pd.read_csv(tmp_path / "raw" / "gpu_batch_relaybp1_bb_d6_p0.001.csv")
    assert sorted(batch.batch_size.unique()) == [1, 16] and len(batch) == 2 * 2 * 3
    runs = pd.read_csv(tmp_path / "raw" / "gpu_runs.csv")
    assert runs.version.iloc[0] == "fake 1.0"
