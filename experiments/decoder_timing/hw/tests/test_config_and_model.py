import numpy as np
import pandas as pd
import pytest

from qechw.__main__ import queue_commands
from qechw.config import load
from qechw.microblossom.board import QS, Timeline, corrected, fit, summary

CFG = load()


def test_relay_configuration():
    r = CFG.relay
    assert r.max_iterations == 36_080
    assert r.hard_bound_ns == 865_920.0
    assert r.decoder_kwargs() == dict(gamma0=0.125, pre_iter=80, set_max_iter=60, num_sets=600, gamma_dist_interval=(-0.24, 0.66))
    int4 = r.variants["relaybp1int4"]
    assert int4.decoder_class == "RelayDecoderI32"
    assert int4.extra_kwargs() == dict(stop_nconv=1, max_data_value=15.0, data_scale_value=2.0)
    assert r.variants["relaybp1"].extra_kwargs() == dict(stop_nconv=1)


def test_runs_and_micro_blossom_settings():
    assert [(r.variant, r.d) for r in CFG.transfer.runs] == [("relaybp1", 12), ("relaybp1", 6), ("relaybp1int4", 12), ("relaybp1int4", 6)]
    assert all(run.variant in CFG.gpu.variants for run in CFG.gpu.runs)
    mb = CFG.microblossom
    assert mb.read_latency_ns(62) / mb.read_latency_ns(93) == pytest.approx(1.30536, rel=1e-5)
    assert {s.suffix for s in mb.collect} == {"", "batch"}


def test_simulation_queues():
    cmds = queue_commands(CFG)
    scripts = [c[-1] for c, _ in cmds]
    assert len(cmds) == 5 and all(c[:4] == ["docker", "exec", "-i", CFG.microblossom.container] for c, _ in cmds)
    assert scripts[2].startswith("cd /root/level2 && cat > queue_b9_.txt && ./prep_slots.sh s9_ b9_ 25 && ")   # slots of the stream run
    assert "run_sim_batch.sh" in scripts[2] and "run_sim_batch.sh" not in scripts[1]
    assert [c[-1] for c, _ in queue_commands(CFG, [1])] == [scripts[1]]
    assert [jobs.count("\n") for _, jobs in cmds] == [50, 16, 75, 16, 8]


def test_job_lines():
    mb = CFG.microblossom
    lines = mb.job_lines(13, ["board", "ours"])
    assert len(lines) == 16 and lines[0].endswith(" 13 62e6 board_d13_c000") and lines[1].endswith(" 14 62e6 ours_d13_c000")
    assert lines[-1] == "/root/level2/inputs/surface_d13_p0.001.graph.json /root/level2/chunks/ours_d13_2500/surface_d13_p0.001.c007.defects 14 62e6 ours_d13_c007"


def _sim(cycles, post_resolve, iterations):
    return pd.DataFrame(dict(cycles=cycles, post_resolve=post_resolve, iterations=iterations))


def test_board_latency_without_spill():
    sim = _sim([93, 186], [0, 2], ["9:0:0", "9:1:2"])            # one loop pass each: nothing spills
    tl = Timeline(sim, num_layers=9)
    assert np.allclose(tl.spill(50.0, 500.0), 0.0)
    assert np.allclose(corrected(sim, 93e6, 50.0, 500.0, tl), [1000 + 50, 2000 + 50 + 1000])


def test_cpu_work_on_an_early_layer_spills_past_the_last():
    # a resolution-heavy iteration on layer 1 finishes after layer 3 is ready
    sim = _sim([0], [0], ["1:0:5 3:0:0"])
    tl = Timeline(sim, num_layers=3)
    assert tl.spill(0.0, 500.0)[0] == pytest.approx(5 * 500 - 2000)


def test_fit_recovers_the_cpu_cost():
    rng = np.random.default_rng(3)
    n = 4000
    sim = _sim(rng.integers(20, 400, n), rng.poisson(1.0, n), ["9:0:0"] * n)
    truth = corrected(sim, 93e6, 40.0, 700.0)
    err, a, b = fit(sim, 93e6, np.quantile(truth, QS), Timeline(sim, 9))
    assert (a, b) == (40.0, 700.0) and err < 1e-9
    assert summary(truth)["max_ns"] == truth.max()


def test_statistics_read_the_per_shot_files_only():
    from qechw.stats import PER_SHOT
    assert PER_SHOT.match("gpu_measured_relaybp1_bb_d6_p0.001.csv.gz") and PER_SHOT.match("fpga_sim_microblossombatch_surface_d9_p0.001.csv.gz")
    assert not any(PER_SHOT.match(n) for n in ("gpu_cupti_relaybp1_bb_d12_p0.001.csv.gz", "gpu_batch_relaybp1_bb_d6_p0.001.csv", "gpu_runs.csv"))
