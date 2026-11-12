"""The bivariate-bicycle syndromes of the transfer and GPU runs.

Same circuits, noise model and file formats as the CPU experiment (qecdec). At the shared error rates the files are the
CPU experiment's (its seeds); the other error rates use the seed 400000 + 1000 d + round(1e5 p).
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import stim
from qecdec import parameters as P2
from qecdec.circuits import noisy_circuit
from qecdec.grid import GridPoint
from qecdec.syndromes import generate, update_index


def seed_for(d: int, p: float) -> int:
    return 400_000 + 1000 * d + int(round(p * 1e5))


def generate_hw(code: str, d: int, p: float, shots: int, outdir: Path) -> dict:
    """Write the files of one grid point with the experiment's own seed (unless they exist); its index row."""
    name = f"{code}_d{d}_p{p:g}"
    circuit = noisy_circuit(code, d, p)
    dem = circuit.detector_error_model()
    seed = seed_for(d, p)
    if not (outdir / f"{name}.dets.b8").exists():
        circuit.to_file(outdir / f"{name}.stim"); dem.to_file(outdir / f"{name}.dem")
        dets, obs = circuit.compile_detector_sampler(seed=seed).sample(shots=shots, separate_observables=True)
        stim.write_shot_data_file(data=dets, path=str(outdir / f"{name}.dets.b8"), format="b8", num_detectors=dem.num_detectors, num_observables=0)
        stim.write_shot_data_file(data=obs, path=str(outdir / f"{name}.obs.b8"), format="b8", num_detectors=0, num_observables=dem.num_observables)
        np.save(outdir / f"{name}.ndet.npy", dets.sum(axis=1).astype(np.int32))
        n_det_mean = float(dets.sum(axis=1).mean())
    else:
        n_det_mean = float(np.load(outdir / f"{name}.ndet.npy").mean())
    return dict(code=code, d=d, p=p, rounds=d, seed=seed, shots=shots, num_qubits=circuit.num_qubits,
                num_detectors=dem.num_detectors, num_errors=dem.num_errors, num_observables=dem.num_observables,
                mean_n_detections=n_det_mean, noise_model=P2.NOISE_MODEL, stim_version=stim.__version__,
                circuit_file=f"{name}.stim", dem_file=f"{name}.dem", decomposed_dem_file="", dets_file=f"{name}.dets.b8",
                obs_file=f"{name}.obs.b8", ndet_file=f"{name}.ndet.npy")


def write_syndromes(outdir: Path, code: str, ds: list[int], ps: list[float], shared_p: list[float], shots: int) -> None:
    outdir.mkdir(parents=True, exist_ok=True)
    rows = []
    for d in ds:
        for p in ps:
            if p in shared_p:
                rows.append(generate(GridPoint(code, d, p), outdir))
            else:
                rows.append(generate_hw(code, d, p, shots, outdir))
            r = rows[-1]
            print(f"{code} d={d} p={p:g} seed={r['seed']} dets={r['num_detectors']} mean_ndet={r['mean_n_detections']:.1f}", flush=True)
    update_index(outdir, rows)
