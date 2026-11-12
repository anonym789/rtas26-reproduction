"""Where the experiment reads and writes its files (paths of config.toml)."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

# columns of every per-shot file in raw/: one row per (shot, pass, counter)
RAW_COLUMNS = ["config_id", "platform", "method", "decoder", "code", "d", "p", "rounds", "shot", "rep",
               "counter_name", "counter_value", "time_ns", "hard_bound_ns", "logical_error", "logical_flips",
               "timing_method", "source"]


def config_id(platform: str, decoder: str, code: str, d: int, p: float) -> str:
    return f"{platform}/{decoder}/{code}/d{d}/p{p:g}"


@dataclass(frozen=True)
class DataDir:
    """root: the output folder (syndromes/, raw/, level2/, stats/); campaign: the campaign the statistics and the
    calibration read, its raw/ and level2/logs* (the recorded one, or root after a new campaign); literature: the
    folder with the Micro Blossom artifact's files (micro_blossom/)."""
    root: Path
    campaign: Path
    literature: Path

    @property
    def raw(self) -> Path:
        return self.root / "raw"

    @property
    def stats(self) -> Path:
        return self.root / "stats"

    @property
    def syndromes(self) -> Path:
        return self.root / "syndromes"

    @property
    def level2(self) -> Path:
        return self.root / "level2"

    @property
    def campaign_raw(self) -> Path:
        return self.campaign / "raw"

    @property
    def campaign_level2(self) -> Path:
        return self.campaign / "level2"

    @property
    def micro_blossom_artifact(self) -> Path:
        """The artifact's files: circuit_level_batch/ (batch means), board/ and board_batch/ (latency histograms)."""
        return self.literature / "micro_blossom"
