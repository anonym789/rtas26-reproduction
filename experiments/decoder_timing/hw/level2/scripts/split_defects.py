#!/usr/bin/env python3
"""Split a Micro Blossom .defects file (int32 little-endian vertex indices, -1 ends a shot) into chunks."""
import sys
from pathlib import Path
import numpy as np
src, outdir, chunk = Path(sys.argv[1]), Path(sys.argv[2]), int(sys.argv[3])
nchunks = int(sys.argv[4]) if len(sys.argv) > 4 else 10**9
v = np.fromfile(src, dtype="<i4")
ends = np.flatnonzero(v == -1)
outdir.mkdir(parents=True, exist_ok=True)
start = 0
for c in range(min(nchunks, (len(ends) + chunk - 1) // chunk)):
    lo_shot, hi_shot = c * chunk, min(len(ends), (c + 1) * chunk)
    lo = 0 if lo_shot == 0 else ends[lo_shot - 1] + 1
    hi = ends[hi_shot - 1] + 1
    v[lo:hi].tofile(outdir / f"{src.stem}.c{c:03d}.defects")
    print(f"chunk {c}: shots {lo_shot}..{hi_shot - 1}")
print("total shots", len(ends))
