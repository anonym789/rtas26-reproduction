"""Grid points (code, distance, error rate) and the jobs of the campaign."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterator

from . import parameters as P


@dataclass(frozen=True)
class GridPoint:
    code: str
    d: int
    p: float

    @property
    def name(self) -> str:
        return f"{self.code}_d{self.d}_p{self.p:g}"

    @property
    def rounds(self) -> int:
        return self.d

    @property
    def shots(self) -> int:
        return P.SHOTS_LARGE_SURFACE if self.code == "surface" and self.d > 17 else P.SHOTS

    @property
    def seed(self) -> int:
        """One fixed seed per grid point (recorded in syndromes/index.csv)."""
        return 100_000 * (P.CODES.index(self.code) + 1) + 1000 * self.d + P.ERROR_RATES.index(self.p) + 1

    @property
    def reps(self) -> int:
        return P.REPS_FOR_CODE.get(self.code, P.REPS)


def grid_points(code: str, decoder: str | None = None) -> Iterator[GridPoint]:
    for d in P.DISTANCES[code]:
        if decoder in ("bposd", "bplsd") and d > P.BPOSD_MAX_D[code]:
            continue
        for p in P.ERROR_RATES:
            yield GridPoint(code, d, p)


def all_jobs() -> Iterator[tuple[str, GridPoint]]:
    """(decoder, grid point) for the whole campaign."""
    for code in P.CODES:
        for decoder in P.DECODERS_FOR_CODE[code]:
            for point in grid_points(code, decoder):
                yield decoder, point


def max_seconds_per_rep(decoder: str, code: str) -> float:
    if code == "bb":
        return P.MAX_SECONDS_PER_REP_BB
    return P.MAX_SECONDS_PER_REP.get(decoder, 1e12)
