"""Regenerates the tables of the recorded campaign (paths.data of config.toml) into paths.check and compares them.

From the recorded campaign's logs and raw files the check collects the simulation tables, runs the calibration and
the statistics, and compares the statistics, the calibration tables and the corrected Micro Blossom rows with the
recorded ones; all must be identical (the rows after decompression). The syndrome index of the output is compared
when the syndromes have been regenerated (`make syndromes`): every row must appear verbatim in the recorded index.
Without a recorded campaign the check is skipped.
"""
from __future__ import annotations

import gzip
from pathlib import Path

from .config import Config
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
    return True, f"{len(rows_new)} of {len(rows_rec)} rows, all as recorded"


def compare_file(new: Path, recorded: Path) -> tuple[bool, str]:
    if not new.exists():
        return False, "missing in the output"
    read = (lambda f: gzip.decompress(f.read_bytes())) if recorded.suffix == ".gz" else (lambda f: f.read_bytes())
    same = read(new) == read(recorded)
    return same, "identical" if same else "differs"


def regenerate(cfg: Config) -> DataDir:
    from .microblossom.calibrate import calibrate
    from .microblossom.logs import collect
    from .stats import write_stats
    data = DataDir(cfg.check, cfg.data, cfg.literature)
    for s in cfg.microblossom.collect:
        collect(data.campaign_level2, data.level2, s, cfg.microblossom.freq_hz[s.d])
    calibrate(data, cfg.microblossom)
    write_stats(data)
    return data


def check(output: DataDir, cfg: Config) -> bool:
    record = cfg.data
    if not (record / "raw").exists():
        print(f"no recorded campaign in {record}: check skipped")
        return True
    data = regenerate(cfg)
    results = [(f"stats/{rec.name}", *compare_file(data.stats / rec.name, rec)) for rec in sorted((record / "stats").glob("*.csv"))]
    results += [(f"raw/{rec.name}", *compare_file(data.raw / rec.name, rec)) for rec in sorted((record / "raw").glob("fpga_sim_*.csv.gz"))]
    index = record / "syndromes" / "index.csv"
    if index.exists():
        results.append(("syndromes/index.csv", *compare_index(output.syndromes / "index.csv", index)))
    for name, ok, verdict in results:
        print(f"{'ok  ' if ok else ('-   ' if ok is None else 'FAIL')} {name:56s} {verdict}")
    return all(ok is not False for _, ok, _ in results)
