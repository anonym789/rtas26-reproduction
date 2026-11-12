"""Parameters of the decoder timing experiment, read once from the settings file and the literature table.

The settings file is config.toml next to the package, or the file named by the environment variable QECDEC_CONFIG
(set by `python -m qecdec --config FILE`; the job queue passes it on). It holds the paths, the grid, the decoders,
the measurement protocol, the checks and the measurement machine. The sourced speed anchor is a row of the
literature table decoder_anchors.csv. Every module reads its values from here.
"""
from __future__ import annotations

import csv
import os
import tomllib
from pathlib import Path

CONFIG = Path(os.environ.get("QECDEC_CONFIG") or Path(__file__).resolve().parents[1] / "config.toml").resolve()
with open(CONFIG, "rb") as _f:
    SETTINGS = tomllib.load(_f)


def _path(key: str) -> Path:
    return (CONFIG.parent / SETTINGS["paths"][key]).resolve()


LITERATURE = _path("literature")
DATA = _path("data")
CAMPAIGN = Path(os.environ["QECDEC_CAMPAIGN"]).resolve() if os.environ.get("QECDEC_CAMPAIGN") else _path("campaign")
OUTPUT = _path("output")
CHECK = _path("check")

# ---------------------------------------------------------------- codes and noise
_grid = SETTINGS["grid"]
CODES: list[str] = _grid["codes"]
DISTANCES: dict[str, list[int]] = _grid["distances"]
BB_INSTANCE = {int(d): name for d, name in _grid["bb_instance"].items()}
ERROR_RATES: list[float] = _grid["error_rates"]
NOISE_MODEL: str = _grid["noise_model"]
SHOTS: int = _grid["shots"]
SHOTS_LARGE_SURFACE: int = _grid["shots_large_surface"]

# ---------------------------------------------------------------- decoders
_dec = SETTINGS["decoders"]
DECODERS: list[str] = _dec["names"]
DECODERS_FOR_CODE: dict[str, list[str]] = _dec["for_code"]
NATIVE_DECODERS = set(_dec["native"])
BPOSD_MAX_D: dict[str, int] = _dec["bposd_max_d"]
BP_MAX_ITER: int = _dec["bp_max_iter"]
BP_METHOD: str = _dec["bp_method"]
OSD_ORDER: int = _dec["osd_order"]
OSD_METHOD: str = _dec["osd_method"]
LSD_ORDER: int = _dec["lsd_order"]
LSD_METHOD: str = _dec["lsd_method"]

# ---------------------------------------------------------------- measurement protocol
_m = SETTINGS["measurement"]
REPS: int = _m["reps"]
REPS_FOR_CODE: dict[str, int] = _m["reps_for_code"]
WARMUP_SHOTS: int = _m["warmup_shots"]
FLOOR_CALLS: int = _m["floor_calls"]
BATCH_SIZE: int = _m["batch_size"]
BATCH_IF_BELOW_X_FLOOR: float = _m["batch_if_below_x_floor"]
MAX_SECONDS_PER_REP: dict[str, int] = _m["max_seconds_per_rep"]
MAX_SECONDS_PER_REP_BB: int = _m["max_seconds_per_rep_bb"]
MIN_SHOTS: int = _m["min_shots"]
SKIP_BPOSD_ABOVE_NS: float = _m["skip_bposd_above_ns"]

# ---------------------------------------------------------------- checks
_c = SETTINGS["checks"]
with open(LITERATURE / "decoder_anchors.csv", newline="") as _f:
    (_anchor,) = [r for r in csv.DictReader(_f) if r["anchor"] == _c["anchor"]]
ANCHOR = dict(decoder=_anchor["decoder"], code=_anchor["code"], d=int(_anchor["d"]), p=float(_anchor["p"]))
ANCHOR_PER_ROUND_NS = float(_anchor["per_round_ns"])
ANCHOR_TOLERANCE: float = _c["anchor_tolerance"]
STABILITY_POINTS = [(s["decoder"], s["code"], s["d"], s["p"]) for s in _c["stability_points"]]
SEED_CHECK_POINT = tuple(_c["seed_check"][k] for k in ("decoder", "code", "d", "p"))
SEED_CHECK_OFFSET: int = _c["seed_check"]["seed_offset"]
