"""Circuits, detector error models and sampled detection events per grid point.

Files per grid point in the syndromes folder (stem = the grid point's name):
  <stem>.stim             noisy circuit
  <stem>.dem              detector error model (hyperedges kept; BP decoders, Chromobius)
  <stem>.decomposed.dem   surface code only: decompose_errors=True (matching decoders)
  <stem>.dets.b8, .obs.b8 Stim b8 format (bit-packed, little endian, one row per shot)
  <stem>.ndet.npy         number of detection events per shot (int32)
and index.csv, one row per grid point.
"""
from __future__ import annotations

import csv
from pathlib import Path

import numpy as np
import stim

from . import parameters as P
from .circuits import noisy_circuit
from .grid import GridPoint


def generate(point: GridPoint, outdir: Path, force: bool = False, seed_offset: int = 0) -> dict:
    """Write the files of one grid point (unless they exist) and return its index row."""
    outdir.mkdir(parents=True, exist_ok=True)
    paths = {k: outdir / f"{point.name}.{ext}" for k, ext in
             [("circuit", "stim"), ("dem", "dem"), ("dets", "dets.b8"), ("obs", "obs.b8"), ("ndet", "ndet.npy")]}
    if point.code == "surface":
        paths["decomposed_dem"] = outdir / f"{point.name}.decomposed.dem"
    seed = point.seed + seed_offset
    circuit = noisy_circuit(point.code, point.d, point.p)
    dem = circuit.detector_error_model()
    if force or not all(path.exists() for path in paths.values()):
        circuit.to_file(paths["circuit"])
        dem.to_file(paths["dem"])
        if point.code == "surface":
            circuit.detector_error_model(decompose_errors=True).to_file(paths["decomposed_dem"])
        sampler = circuit.compile_detector_sampler(seed=seed)
        dets, obs = sampler.sample(shots=point.shots, separate_observables=True)
        stim.write_shot_data_file(data=dets, path=str(paths["dets"]), format="b8",
                                  num_detectors=dem.num_detectors, num_observables=0)
        stim.write_shot_data_file(data=obs, path=str(paths["obs"]), format="b8",
                                  num_detectors=0, num_observables=dem.num_observables)
        np.save(paths["ndet"], dets.sum(axis=1).astype(np.int32))
        n_det_mean = float(dets.sum(axis=1).mean())
    else:
        n_det_mean = float(np.load(paths["ndet"]).mean())
    return dict(code=point.code, d=point.d, p=point.p, rounds=point.rounds, seed=seed, shots=point.shots,
                num_qubits=circuit.num_qubits, num_detectors=dem.num_detectors, num_errors=dem.num_errors,
                num_observables=dem.num_observables, mean_n_detections=n_det_mean,
                noise_model=P.NOISE_MODEL, stim_version=stim.__version__,
                circuit_file=paths["circuit"].name, dem_file=paths["dem"].name,
                decomposed_dem_file=paths["decomposed_dem"].name if point.code == "surface" else "",
                dets_file=paths["dets"].name, obs_file=paths["obs"].name, ndet_file=paths["ndet"].name)


def update_index(outdir: Path, rows: list[dict]) -> None:
    """Merge rows into outdir/index.csv (one row per grid point, in grid order)."""
    index = outdir / "index.csv"
    merged = {}
    if index.exists():
        with open(index) as f:
            for r in csv.DictReader(f):
                merged[(r["code"], int(r["d"]), float(r["p"]))] = r
    for r in rows:
        merged[(r["code"], r["d"], r["p"])] = r
    with open(index, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        for k in sorted(merged, key=lambda k: (P.CODES.index(k[0]), k[1], k[2])):
            w.writerow(merged[k])


def read_index(syndromes: Path, point: GridPoint) -> dict:
    with open(syndromes / "index.csv") as f:
        for r in csv.DictReader(f):
            if r["code"] == point.code and int(r["d"]) == point.d and abs(float(r["p"]) - point.p) < 1e-12:
                return r
    raise SystemExit(f"grid point {point.code} d={point.d} p={point.p} not in {syndromes}/index.csv; "
                     "run `python -m qecdec syndromes` first")


def load_b8(path: Path, num_bits: int, max_rows: int | None = None) -> np.ndarray:
    """Rows of a Stim b8 file as a 0/1 array."""
    row_bytes = (num_bits + 7) // 8
    raw = np.fromfile(path, dtype=np.uint8)
    rows = raw.size // row_bytes
    if max_rows is not None:
        rows = min(rows, max_rows)
    raw = raw[: rows * row_bytes].reshape(rows, row_bytes)
    return np.unpackbits(raw, axis=1, bitorder="little")[:, :num_bits]
