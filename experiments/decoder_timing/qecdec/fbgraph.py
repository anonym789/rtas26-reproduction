"""The PyMatching matching graph of a surface-code DEM as a fusion-blossom graph (JSON).

fusion-blossom has no Stim DEM reader. To make both matching decoders solve the same problem, the graph
is taken from PyMatching's own DEM parser (`pymatching.Matching.from_detector_error_model`, merge
strategy "independent"), so vertices, edges, merged probabilities and observable masks are identical.

Weights: PyMatching uses w = log((1-p)/p) as floats. fusion-blossom needs integer (even) weights; as in
its example codes (`compute_weights(max_half_weight)`) they are scaled to w_int = 2 round(w / w_max
max_half_weight) with max_half_weight = 500. Boundary edges get one virtual vertex per real vertex, as
in fusion-blossom's own planar codes ("each real vertex only connects to one nearest virtual vertex").
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pymatching
import stim

from .grid import GridPoint

MAX_HALF_WEIGHT = 500


def convert(dem: stim.DetectorErrorModel) -> dict:
    m = pymatching.Matching.from_detector_error_model(dem)
    edges = m.edges()  # list of (u, v|None, {"fault_ids", "weight", "error_probability"})
    num_det = m.num_detectors
    weights = np.array([e[2]["weight"] for e in edges], dtype=float)
    if (weights < 0).any():
        raise ValueError("negative edge weight (p > 0.5) not supported")
    w_max = weights.max()
    w_int = (2 * np.round(weights / w_max * MAX_HALF_WEIGHT)).astype(int)
    vertex_num = num_det
    virtual_of = {}
    weighted_edges, masks, virtual_vertices = [], [], []
    for (u, v, attrs), w in zip(edges, w_int):
        mask = 0
        for f in attrs["fault_ids"]:
            mask |= 1 << int(f)
        if v is None:
            if u not in virtual_of:
                virtual_of[u] = vertex_num
                virtual_vertices.append(vertex_num)
                vertex_num += 1
            v = virtual_of[u]
        weighted_edges.append([int(u), int(v), int(w)])
        masks.append(int(mask))
    return dict(vertex_num=vertex_num, num_detectors=num_det,
                num_observables=m.num_fault_ids, weighted_edges=weighted_edges,
                virtual_vertices=virtual_vertices, edge_masks=masks,
                weight_scale=float(MAX_HALF_WEIGHT * 2 / w_max), max_half_weight=MAX_HALF_WEIGHT,
                pymatching_version=pymatching.__version__)


def write_graph(syndromes: Path, point: GridPoint) -> dict:
    """<stem>.fbgraph.json next to the grid point's decomposed DEM."""
    dem = stim.DetectorErrorModel.from_file(syndromes / f"{point.name}.decomposed.dem")
    g = convert(dem)
    (syndromes / f"{point.name}.fbgraph.json").write_text(json.dumps(g))
    return g
