"""Regenerates the statistics of the recorded campaign (paths.data of config.toml) into paths.check and compares them.

The statistics of the recorded campaign must be identical byte for byte to the recorded ones. The syndrome index of
the output is compared when the syndromes have been regenerated (`make syndromes`): every row must appear verbatim
in the recorded index, which may list more grid points than were regenerated. Without a recorded campaign the
check is skipped.
"""
from __future__ import annotations

from pathlib import Path

from .data import DataDir


def compare_index(new: Path, recorded: Path) -> tuple[bool | None, str]:
    if not new.exists():
        return None, "not built (make syndromes)"
    header_new, *rows_new = new.read_text().splitlines()
    header_rec, *rows_rec = recorded.read_text().splitlines()
    if header_new != header_rec:
        return False, "header differs"
    foreign = set(rows_new) - set(rows_rec)
    if foreign:
        return False, f"{len(foreign)} of {len(rows_new)} rows not in the record"
    return True, f"{len(rows_new)} of {len(rows_rec)} grid points, all as recorded"


def check(output: DataDir, record: Path, out: Path) -> bool:
    if not (record / "raw").exists():
        print(f"no recorded campaign in {record}: check skipped")
        return True
    from .stats import write_stats
    regenerated = DataDir(out, record)
    write_stats(regenerated)
    results = []
    for rec in sorted((record / "stats").glob("*.csv")):
        new = regenerated.stats / rec.name
        same = new.exists() and new.read_bytes() == rec.read_bytes()
        results.append((f"stats/{rec.name}", same, "identical" if same else ("differs" if new.exists() else "missing in the output")))
    index = record / "syndromes" / "index.csv"
    if index.exists():
        results.append(("syndromes/index.csv", *compare_index(output.syndromes / "index.csv", index)))
    for name, ok, verdict in results:
        print(f"{'ok  ' if ok else ('-   ' if ok is None else 'FAIL')} {name:24s} {verdict}")
    return all(ok is not False for _, ok, _ in results)
