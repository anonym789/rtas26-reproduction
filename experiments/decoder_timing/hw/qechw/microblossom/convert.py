"""The CPU experiment's surface-code syndromes in the input format of the Micro Blossom tool flow.

Micro Blossom (arXiv 2502.14787, repository commit 468af5d) builds its hardware from a fusion-blossom
"Syndrome Pattern v1.0" file (initializer, positions, one defect list per shot); its own CLI
(`micro_blossom parser`) turns that file into the hardware graph JSON and the binary defects file
that the embedded program and the cycle-accurate simulator read.

Graph: the CPU experiment's fusion-blossom graph of the same DEM (`syndromes/<name>.fbgraph.json`, built from
PyMatching's DEM parser, qecdec.fbgraph, integer weights with max_half_weight 500)
re-quantised to the 4-bit weights of the published design (max_half_weight = 7, as in
benchmark/hardware/frequency_optimization/circuit_level_final/run.py). As in the artifact's
`transform-syndromes qecp-rotated-planar-code`, the boundary is merged into two virtual vertices
(vertex 0: the boundary whose edges flip the logical observable, vertex 1: the opposite boundary),
which keeps the matching problem identical (virtual vertices absorb any number of defects).
Only the connected half of the graph that carries the logical observable is kept (the Z-type
detectors of the Z-memory experiment, i.e. the X-error decoding problem): the CPU experiment's graph holds both
halves, which are disconnected, while the published design decodes one basis (only_stab_z in the
artifact's graph builder); a full system runs one decoder instance per basis.
Positions come from Stim's detector coordinates (i = x, j = y, t = 2 * round index); the two
virtual vertices sit at the mean position of their neighbours, at the middle time, as in the artifact.

Outputs (in level2/inputs): <name>.syndromes, <name>.edge_masks.json (observable mask per edge, for the
parity reporters), <name>.convert.json (provenance).
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import stim

MAX_HALF_WEIGHT = 7   # 4-bit weights of the published design


def convert(syndromes: Path, d: int, p: float, out: Path, shots: int = 0) -> dict:
    """Write the Micro Blossom input of one grid point into out; returns the provenance record."""
    name = f"surface_d{d}_p{p:g}"
    g = json.loads((syndromes / f"{name}.fbgraph.json").read_text())
    circ = stim.Circuit.from_file(str(syndromes / f"{name}.stim"))
    num_det = g["num_detectors"]
    assert circ.num_detectors == num_det
    coords = circ.get_detector_coordinates()
    virt = set(g["virtual_vertices"])
    # ---- keep the connected component(s) of real detectors that touch an observable-flipping edge
    parent = list(range(g["vertex_num"]))
    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]; x = parent[x]
        return x
    for (u, v, w) in g["weighted_edges"]:
        if u not in virt and v not in virt:
            parent[find(u)] = find(v)
    obs_roots = {find(u if u not in virt else v) for (u, v, w), m in zip(g["weighted_edges"], g["edge_masks"]) if m & 1}
    keep = [k for k in range(num_det) if find(k) in obs_roots]
    # ---- vertices: 0, 1 = merged boundaries; kept real detector keep[i] -> i + 2
    new_index = {k: i + 2 for i, k in enumerate(keep)}
    edges, masks, nb = [], [], {0: [], 1: []}
    seen = set()
    for (u, v, w), m in zip(g["weighted_edges"], g["edge_masks"]):
        half = max(1, int(round(w / 2 / g["max_half_weight"] * MAX_HALF_WEIGHT)))
        real_end = v if u in virt else u
        if real_end not in new_index:
            continue                                   # other basis
        if v in virt or u in virt:
            real = u if v in virt else v
            side = 0 if (m & 1) else 1
            a_, b_ = new_index[real], side
            nb[side].append(real)
        else:
            a_, b_ = new_index[u], new_index[v]
        key = (min(a_, b_), max(a_, b_))
        if key in seen:
            raise SystemExit(f"parallel edge {key}: merge needed")
        seen.add(key)
        edges.append([a_, b_, 2 * half])
        masks.append(int(m))
    ts = sorted({coords[k][2] for k in keep})
    tmid = 2 * int(round((ts[0] + ts[-1]) / 2))
    pos = []
    for side in (0, 1):
        xs = [coords[k][0] for k in nb[side]]; ys = [coords[k][1] for k in nb[side]]
        pos.append({"i": float(np.mean(xs)), "j": float(np.mean(ys)), "t": float(tmid)})
    for k in keep:
        x, y, t = coords[k][:3]
        pos.append({"i": float(x), "j": float(y), "t": float(2 * round(t))})
    init = {"vertex_num": len(keep) + 2, "weighted_edges": edges, "virtual_vertices": [0, 1]}
    # ---- syndromes
    rb = (num_det + 7) // 8
    raw = np.fromfile(syndromes / f"{name}.dets.b8", dtype=np.uint8)
    n_total = raw.size // rb
    n = min(shots, n_total) if shots else n_total
    bits = np.unpackbits(raw[: n * rb].reshape(n, rb), axis=1, bitorder="little")[:, :num_det]
    out.mkdir(parents=True, exist_ok=True)
    with open(out / f"{name}.syndromes", "w") as f:
        f.write("Syndrome Pattern v1.0   <initializer> <positions> <syndrome_pattern>*\n")
        f.write(json.dumps(init, separators=(",", ":")) + "\n")
        f.write(json.dumps(pos, separators=(",", ":")) + "\n")
        keep_arr = np.array(keep)
        kept_bits = bits[:, keep_arr]
        for row in kept_bits:
            dv = (np.flatnonzero(row) + 2).tolist()
            f.write(json.dumps({"defect_vertices": dv, "erasures": [], "dynamic_weights": []}, separators=(",", ":")) + "\n")
    (out / f"{name}.edge_masks.json").write_text(json.dumps(masks))
    hist = np.bincount([e[2] for e in edges])
    np.save(out / f"{name}.kept_detectors.npy", keep_arr)
    prov = dict(source=f"E2 syndromes/{name} (.fbgraph.json, .stim, .dets.b8)", shots=int(n), num_detectors=num_det,
                kept_detectors=len(keep), basis="component carrying the logical observable (Z-type detectors)",
                vertex_num=len(keep) + 2, edges=len(edges), boundary_edges={"0": len(nb[0]), "1": len(nb[1])},
                layers=len(ts), max_half_weight=MAX_HALF_WEIGHT,
                weight_histogram={str(i): int(c) for i, c in enumerate(hist) if c},
                mean_defects=float(kept_bits.sum(axis=1).mean()), mean_defects_both_bases=float(bits.sum(axis=1).mean()))
    (out / f"{name}.convert.json").write_text(json.dumps(prov, indent=1))
    return prov

