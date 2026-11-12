"""Where the experiment reads and writes its files (paths of config.toml)."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .grid import GridPoint


@dataclass(frozen=True)
class DataDir:
    """root: the output folder (syndromes/, raw/ of new measurements, stats/); campaign: the campaign the
    statistics and checks read, its raw/ and syndromes/index.csv (the recorded one, or root after a new campaign)."""
    root: Path
    campaign: Path

    @property
    def syndromes(self) -> Path:
        return self.root / "syndromes"

    @property
    def raw(self) -> Path:
        return self.root / "raw"

    @property
    def stats(self) -> Path:
        return self.root / "stats"

    @property
    def campaign_raw(self) -> Path:
        return self.campaign / "raw"

    @property
    def campaign_index(self) -> Path:
        return self.campaign / "syndromes" / "index.csv"

    def raw_file(self, decoder: str, point: GridPoint, subdir: str | None = None, base: Path | None = None) -> Path:
        """<raw>/<decoder>_<grid point>.csv.gz, in the output unless base is given; check runs go into subfolders
        (stability/<time>, seedcheck)."""
        folder = base or self.raw
        return (folder / subdir if subdir else folder) / f"{decoder}_{point.name}.csv.gz"

    def campaign_raw_file(self, decoder: str, point: GridPoint, subdir: str | None = None) -> Path:
        return self.raw_file(decoder, point, subdir, base=self.campaign_raw)
