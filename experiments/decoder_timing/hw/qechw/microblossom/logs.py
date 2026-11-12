"""The cycle-accurate simulation logs as tidy per-shot tables.

Each log (level2/<logs>/<source>_d<d>_c<chunk>.log) holds one line per shot printed by the instrumented embedded
benchmark (benchmark_decoding.rs with patches/e4_instrumentation.diff, print only):
  [<k>] time: <us>us, counter: <instructions>, wall: <us>us, e4: <post_find> <post_resolve> <total_find> <total_resolve> <cycles>
  cycles        accelerator clock cycles from "last syndrome layer ready" to "decoding finished"
                (load-stall emulator, 1 us measurement cycle), as on the board
  instructions  hardware instruction counter of the shot (all CPU -> accelerator instructions)
  post_find     obstacle reads by the CPU after the final layer was loaded (on the latency path)
  post_resolve  obstacles resolved by the CPU primal module after the final layer was loaded
  total_find, total_resolve  the same over the whole shot
followed by one line per shot
  e4l: <layers loaded>:<obstacle reads>:<resolutions> ...   one entry per CPU loop iteration
stored as the string column `iterations`, and, with patches/e4_matching.diff (print only, after the timed region),
  e4m: <node>-<node> | <node>-v<virtual vertex> ...         final matching of the CPU primal module
stored as the string column `matching` (empty for logs without that patch).

A chunk counts only if its last line is SIM_EXIT 0, it holds no NUL bytes and it reports the build parameter of its
mode (USE_LAYER_FUSION: true for stream, false for batch). Output: sim_<source>_d<d>_p<p>[_<tag>].csv.gz in the
output's level2/, one row per shot (shot = global index).
"""
from __future__ import annotations

import re
from pathlib import Path

import pandas as pd

from ..config import CollectSet

LINE = re.compile(r"^\[(\d+)\] time: ([0-9.]+)us, counter: (\d+), wall: [0-9.]+us, e4: (\d+) (\d+) (\d+) (\d+) (\d+)\s*$")
COLUMNS = ["shot", "time_us_printed", "instructions", "post_find", "post_resolve", "total_find", "total_resolve",
           "cycles", "iterations", "matching"]


def collect(campaign_level2: Path, out: Path, s: CollectSet, freq_hz: float) -> Path | None:
    """Write the table of one log set of the campaign into out; None if the set has no complete chunk."""
    logs = campaign_level2 / s.log_folder
    want = b"USE_LAYER_FUSION: " + (b"false" if s.mode == "batch" else b"true")
    frames, status = [], []
    for f in sorted(logs.glob(f"{s.source}_d{s.d}_c[0-9][0-9][0-9].log")):
        chunk = int(f.stem.rsplit("_c", 1)[1])
        raw = f.read_bytes()
        exits = re.findall(rb"SIM_EXIT (\d+)", raw)
        ok = bool(exits) and exits[-1] == b"0" and b"\x00" not in raw and want in raw
        rows = []
        for ln in raw.decode("utf8", "replace").splitlines():
            m = LINE.match(ln)
            if m:
                k, t_us, instr, pf, pr, tf, tr, cyc = m.groups()
                rows.append([chunk * s.chunk + int(k) - 1, float(t_us), int(instr), int(pf), int(pr), int(tf), int(tr), int(cyc), "", ""])
            elif ln.startswith("e4l:") and rows:
                rows[-1][-2] = ln[4:].strip()
            elif ln.startswith("e4m:") and rows:
                rows[-1][-1] = ln[4:].strip()
        status.append(dict(chunk=chunk, shots=len(rows), complete=ok))
        if ok:
            frames.append(pd.DataFrame(rows, columns=COLUMNS))
    if not frames:
        return None
    st = pd.DataFrame(status)
    df = pd.concat(frames, ignore_index=True).sort_values("shot")
    df["sim_ns"] = df.cycles / freq_hz * 1e9
    out.mkdir(parents=True, exist_ok=True)
    table = out / f"sim_{s.source}_d{s.d}_p{s.p:g}{'_' + s.suffix if s.suffix else ''}.csv.gz"
    df.to_csv(table, index=False, compression="gzip")
    print(f"{table.name}: {len(df)} shots from {int(st.complete.sum())}/{len(st)} complete chunks; "
          f"incomplete: {st[~st.complete].chunk.tolist()}")
    return table
