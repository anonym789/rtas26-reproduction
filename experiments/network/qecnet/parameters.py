"""Parameters of the network experiment, read once from the settings file and the literature tables.

The settings file is config.toml next to the package, or the file named by the environment variable QECNET_CONFIG
(set by `python -m qecnet --config FILE`; worker processes inherit it). It holds the paths and the settings of the
runs: the sweep, the scenarios, the simulated cycles and seeds, the R x L grid. The sourced constants are the
literature table network_parameters.csv (one row per value, with its source); the links are network_links.csv
(links.py). Every module reads its values from here.
"""
from __future__ import annotations

import csv
import os
import tomllib
from pathlib import Path

CONFIG = Path(os.environ.get("QECNET_CONFIG") or Path(__file__).resolve().parents[1] / "config.toml").resolve()
with open(CONFIG, "rb") as _f:
    _settings = tomllib.load(_f)


def _path(key: str) -> Path:
    return (CONFIG.parent / _settings["paths"][key]).resolve()


LITERATURE = _path("literature")
DATA = _path("data")
RUNS = _path("runs")
OUTPUT = _path("output")
CHECK = _path("check")
WORKERS = _settings["simulate"]["workers"]

with open(LITERATURE / "network_parameters.csv", newline="") as _f:
    _values: dict[str, list[dict]] = {}
    for _row in csv.DictReader(_f):
        _values.setdefault(_row["parameter"], []).append(_row)


def _value(name: str, kind: type):
    (row,) = _values[name]
    return kind(row["value"])


def _sourced(name: str) -> dict[int, str]:
    """The values of a parameter with several sourced values, in table order, and their sources."""
    return {int(row["value"]): row["source"] for row in _values[name]}


# ---------------------------------------------------------------- cycle and budgets
CYCLE_NS = _value("cycle_ns", float)
MS_CYCLE_NS = _value("ms_cycle_ns", float)
BUDGETS_NS = {"cycle": CYCLE_NS, "reaction": _value("reaction_budget_ns", float)}

# ---------------------------------------------------------------- load model
QUBITS_PER_CONTROLLER_SOURCE = _sourced("qubits_per_controller")
QUBITS_PER_CONTROLLER = list(QUBITS_PER_CONTROLLER_SOURCE)
BITS_PER_OUTCOME_SOURCE = _sourced("bits_per_outcome")
BITS_PER_OUTCOME = list(BITS_PER_OUTCOME_SOURCE)
HEADER_BITS = _value("header_bits", int)
ETH_OVERHEAD_BITS = _value("eth_overhead_bits", int)
ETH_MIN_WIRE_BITS = _value("eth_min_wire_bits", int)

# ---------------------------------------------------------------- nodes
AGGREGATION_DELAY_NS = _value("aggregation_delay_ns", float)
PORT_CAP_K = _value("port_cap_k", int)
ROOT_MAX_PORTS = _value("root_max_ports", int)

# ---------------------------------------------------------------- sweep
_sweep = _settings["sweep"]
TOPOLOGY_LINKS: dict[str, list[str]] = _sweep["links"]
TOPOLOGY_AGGREGATION: dict[str, list[int]] = _sweep["aggregation"]
N_VALUES: list[int] = _sweep["n"]
N1_LINKS: dict[str, str] = _sweep["n1_links"]

_scenarios = _settings["scenarios"]
SCENARIOS = {name: dict(b=s["b"], d=s.get("d")) for name, s in _scenarios.items()}
S3_D_SWEEP = {(e["topology"], e["link"]): e["d"] for e in _scenarios["S3"]["d_sweep"]}
S3_TOPOLOGIES: list[str] = _scenarios["S3"]["topologies"]

# ---------------------------------------------------------------- simulated cycles and seeds
_cycles = _settings["cycles"]
WARMUP_CYCLES = _cycles["warmup"]
RECORDED_CYCLES = _cycles["recorded"]
JITTER_CYCLES = _cycles["jitter"]
JITTER_CYCLES_SMALL_N = _cycles["jitter_small_n"]
JITTER_SMALL_N = _cycles["small_n"]
BASE_SEED = _cycles["seed"]

# ---------------------------------------------------------------- R x L grid (bound; diagonal also simulated)
_grid = _settings["grid"]
GRID_RATES_GBPS: list[int] = _grid["rates_gbps"]
GRID_LATENCIES_NS: list[int] = _grid["latencies_ns"]
GRID_TOPOLOGIES: list[str] = _grid["topologies"]
GRID_SCENARIOS: list[str] = _grid["scenarios"]
GRID_DIAGONAL = list(zip(GRID_RATES_GBPS, GRID_LATENCIES_NS))

# ---------------------------------------------------------------- saturation anchor
ANCHOR_CYCLE_NS = _value("anchor_cycle_ns", float)
ANCHOR_FRAME_BITS = _value("anchor_frame_bits", int)
