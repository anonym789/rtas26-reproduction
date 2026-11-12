"""Where the experiment reads its simulation runs and writes its tables (paths of config.toml)."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class DataDir:
    """root: the output folder (load/, bound/, sim/stats/, new runs in sim/raw/); runs: the folder of the
    simulation runs that the statistics and checks read (the recorded runs, or root/sim/raw after a new campaign)."""
    root: Path
    runs: Path

    @property
    def load(self) -> Path:
        return self.root / "load"

    @property
    def bound(self) -> Path:
        return self.root / "bound"

    @property
    def stats(self) -> Path:
        return self.root / "sim" / "stats"

    def runs_folder(self, subfolder: str) -> Path:
        """Recorded runs of a job set: the sweeps in runs/, the other job sets in runs/checks and runs/edge."""
        return self.runs / subfolder if subfolder else self.runs

    def new_runs_folder(self, subfolder: str) -> Path:
        """Where `simulate` writes the runs of a job set."""
        new = self.root / "sim" / "raw"
        return new / subfolder if subfolder else new
