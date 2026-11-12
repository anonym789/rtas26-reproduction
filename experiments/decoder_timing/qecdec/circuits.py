"""Memory circuits of the three code families, all with the same noise model."""
from __future__ import annotations

import sys
from pathlib import Path

import stim

from .parameters import BB_INSTANCE

VENDOR = Path(__file__).resolve().parents[1] / "vendor"
# the circuit generators and the noise model of Chromobius v1.1.1 are vendored as plain modules (vendor/VENDOR.md)
sys.path.insert(0, str(VENDOR / "chromobius_v1.1.1"))
import gen  # noqa: E402
from clorco._make_circuit import make_circuit  # noqa: E402


def _surface(d: int) -> stim.Circuit:
    c = stim.Circuit.generated("surface_code:rotated_memory_z", distance=d, rounds=d,
                               after_clifford_depolarization=1e-3, before_round_data_depolarization=1e-3,
                               before_measure_flip_probability=1e-3, after_reset_flip_probability=1e-3)
    return c.without_noise()


def _colour(d: int) -> stim.Circuit:
    c = make_circuit(style="superdense_color_code_Z", noise_model=None, noise_strength=0,
                     rounds=d, diameter=d, convert_to_cz=False, editable_extras={})
    return c.without_noise()


def _bivariate_bicycle(d: int) -> stim.Circuit:
    return stim.Circuit.from_file(VENDOR / "tesseract_circuits" / f"{BB_INSTANCE[d]}.noiseless.stim")


NOISELESS = {"surface": _surface, "color": _colour, "bb": _bivariate_bicycle}


def noisy_circuit(code: str, d: int, p: float) -> stim.Circuit:
    """The noiseless memory circuit with uniform depolarising noise of strength p."""
    return gen.NoiseModel.uniform_depolarizing(p).noisy_circuit(NOISELESS[code](d))
