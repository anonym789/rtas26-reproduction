"""Split X/Z decoding matrices for a Stim memory-experiment DEM.

IBM's decoders decode sigma_X and sigma_Z independently with derived check
matrices H_X and H_Z (arXiv 2510.21600 sec. 2; construction in arXiv 2506.01779
appendix p. 7): H_X, the matrix of the *X-error* decoder, is H restricted to the
rows of the Z-type detectors (Z checks detect X errors), H_Z is H restricted to
the X-type detector rows; columns with identical restricted support are merged
into one error whose probability is that of an odd number of the merged events.
Naming here follows IBM: basis "X" = X-error decoder (Z-type detector rows,
carries the Z-memory observables), basis "Z" = Z-error decoder (X-type rows).

Detector basis comes from the 4th detector coordinate of the tesseract-decoder
circuits (Chromobius convention: 0-2 = X-type red/green/blue, 3-5 = Z-type).
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import scipy.sparse as sp
import stim
from beliefmatching import detector_error_model_to_check_matrices


@dataclass
class XZMatrices:
    H: dict[str, sp.csc_matrix]          # error type -> check matrix (detector rows of the other type x merged errors)
    priors: dict[str, np.ndarray]
    obs: dict[str, sp.csc_matrix]        # basis -> observables matrix (num_obs x merged errors)
    det_index: dict[str, np.ndarray]     # error type -> indices (in the full DEM) of the detectors its decoder reads
    num_detectors: int
    num_observables: int


def detector_basis(circuit: stim.Circuit) -> np.ndarray:
    """0 = X-type, 1 = Z-type per detector, from the 4th coordinate (0-2 -> X, 3-5 -> Z)."""
    coords = circuit.get_detector_coordinates()
    b = np.zeros(circuit.num_detectors, dtype=np.int8)
    for i in range(circuit.num_detectors):
        c = coords[i]
        if len(c) < 4:
            raise ValueError(f"detector {i} has no basis coordinate: {c}")
        b[i] = 0 if int(c[3]) < 3 else 1
    return b


def _merge_columns(Hp: sp.csc_matrix, priors: np.ndarray, Ap: sp.csc_matrix):
    """Merge columns with identical (check, observable) support; drop empty columns."""
    Hp = Hp.tocsc(); Ap = Ap.tocsc()
    keys = {}
    order = []
    for j in range(Hp.shape[1]):
        rows = tuple(Hp.indices[Hp.indptr[j]:Hp.indptr[j + 1]])
        orows = tuple(Ap.indices[Ap.indptr[j]:Ap.indptr[j + 1]])
        if not rows:
            continue  # error invisible to this decoder
        k = (rows, orows)
        if k not in keys:
            keys[k] = len(order)
            order.append([k, 1.0])
        order[keys[k]][1] *= (1.0 - 2.0 * priors[j])  # product of (1 - 2 p_i)
    n = len(order)
    rows_i, cols_i, orows_i, ocols_i = [], [], [], []
    p = np.empty(n)
    for j, ((rows, orows), prod) in enumerate(order):
        p[j] = 0.5 * (1.0 - prod)  # probability of an odd number of merged events
        rows_i.extend(rows); cols_i.extend([j] * len(rows))
        orows_i.extend(orows); ocols_i.extend([j] * len(orows))
    H = sp.csc_matrix((np.ones(len(rows_i), dtype=np.uint8), (rows_i, cols_i)), shape=(Hp.shape[0], n))
    A = sp.csc_matrix((np.ones(len(orows_i), dtype=np.uint8), (orows_i, ocols_i)), shape=(Ap.shape[0], n))
    return H, p, A


def xz_matrices(circuit: stim.Circuit, dem: stim.DetectorErrorModel | None = None) -> XZMatrices:
    dem = dem or circuit.detector_error_model()
    m = detector_error_model_to_check_matrices(dem, allow_undecomposed_hyperedges=True)
    Hfull = m.check_matrix.tocsr()
    Afull = m.observables_matrix.tocsc()
    priors = np.asarray(m.priors, dtype=float)
    basis = detector_basis(circuit)
    out = XZMatrices(H={}, priors={}, obs={}, det_index={}, num_detectors=dem.num_detectors,
                     num_observables=dem.num_observables)
    # X-error decoder reads the Z-type detectors (basis code 1) and owns the Z-memory observables;
    # Z-error decoder reads the X-type detectors (basis code 0) and has no observables here.
    for name, b in (("X", 1), ("Z", 0)):
        idx = np.where(basis == b)[0]
        Hp = Hfull[idx, :].tocsc()
        Ap = Afull if name == "X" else sp.csc_matrix((Afull.shape[0], Afull.shape[1]), dtype=np.uint8)
        H, p, A = _merge_columns(Hp, priors, Ap)
        out.H[name], out.priors[name], out.obs[name], out.det_index[name] = H, p, A, idx
    return out
