from dataclasses import dataclass

from .geo import LonLat


@dataclass(frozen=True)
class RouteGeometry:
    """A drivable path with distance (mi) and drive time (s) accumulated at every vertex."""

    label: str
    points: list[LonLat]
    cum_miles: list[float]
    cum_seconds: list[float]

    @property
    def distance_mi(self) -> float:
        return self.cum_miles[-1]

    @property
    def duration_s(self) -> float:
        return self.cum_seconds[-1]
