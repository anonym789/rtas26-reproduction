import json

import pymatching
import stim

from qecdec.fbgraph import MAX_HALF_WEIGHT, convert, write_graph
from qecdec.grid import GridPoint
from qecdec.syndromes import generate


def test_graph_matches_pymatching(tmp_path):
    pt = GridPoint("surface", 5, 0.003)
    generate(pt, tmp_path)
    g = write_graph(tmp_path, pt)
    assert json.loads((tmp_path / f"{pt.name}.fbgraph.json").read_text()) == g
    dem = stim.DetectorErrorModel.from_file(tmp_path / f"{pt.name}.decomposed.dem")
    m = pymatching.Matching.from_detector_error_model(dem)
    assert g["num_detectors"] == m.num_detectors
    assert len(g["weighted_edges"]) == len(m.edges())
    # every boundary edge ends at its own virtual vertex, one per real vertex
    assert g["vertex_num"] == m.num_detectors + len(g["virtual_vertices"])
    weights = [w for _, _, w in g["weighted_edges"]]
    assert all(w % 2 == 0 for w in weights) and max(weights) == 2 * MAX_HALF_WEIGHT


def test_convert_is_deterministic(tmp_path):
    pt = GridPoint("surface", 3, 0.001)
    generate(pt, tmp_path)
    dem = stim.DetectorErrorModel.from_file(tmp_path / f"{pt.name}.decomposed.dem")
    assert convert(dem) == convert(dem)
