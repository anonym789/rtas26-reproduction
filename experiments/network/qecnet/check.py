"""Regenerates the tables of the recorded campaign (paths.data of config.toml) into paths.check and compares them.

The load model, the bounds and the statistics of the recorded runs must be identical byte for byte to the
recorded tables. Without a recorded campaign the check is skipped.
"""
from __future__ import annotations

from pathlib import Path

from .data import DataDir


def regenerate(record: Path, out: Path) -> DataDir:
    from .bounds import write_bounds
    from .frames import frame_size_table
    from .stats import write_stats
    data = DataDir(out, record / "sim" / "raw")
    data.load.mkdir(parents=True, exist_ok=True)
    frame_size_table().to_csv(data.load / "frame_sizes.csv", index=False)
    write_bounds(data)
    write_stats(data)
    return data


def compare(new: Path, recorded: Path) -> tuple[bool, str]:
    if not new.exists():
        return False, "missing in the output"
    same = new.read_bytes() == recorded.read_bytes()
    return same, "identical" if same else "differs"


def check(record: Path, out: Path) -> bool:
    if not (record / "sim" / "raw").exists():
        print(f"no recorded campaign in {record}: check skipped")
        return True
    data = regenerate(record, out)
    ok_all = True
    for rec in sorted(record.glob("load/*.csv")) + sorted(record.glob("bound/*.csv")) + sorted(record.glob("sim/stats/*.csv")):
        rel = rec.relative_to(record)
        ok, verdict = compare(data.root / rel, rec)
        ok_all &= ok
        print(f"{'ok  ' if ok else 'FAIL'} {str(rel):28s} {verdict}")
    return ok_all
