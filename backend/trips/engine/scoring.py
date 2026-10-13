"""Per-route risk totals and the recommendation order from the brief."""

from dataclasses import dataclass
from itertools import pairwise

from .risk import Level


@dataclass(frozen=True)
class RouteSummary:
    miles_by_level: dict[Level, float]
    avg_risk: float  # distance-weighted mean level, 0..4
    max_level: Level

    def miles(self, level: Level) -> float:
        return self.miles_by_level[level]


@dataclass(frozen=True)
class Candidate:
    route_id: str
    summary: RouteSummary
    duration_s: float


@dataclass(frozen=True)
class Recommendation:
    route_id: str
    reason: str
    ranking: list[str]
    all_blocked: bool


def segment_levels(levels: list[Level]) -> list[Level]:
    """The stretch between two checkpoints is as risky as the worse of them."""
    return [max(a, b) for a, b in pairwise(levels)]


def summarize(miles: list[float], levels: list[Level]) -> RouteSummary:
    by_level = {lvl: 0.0 for lvl in Level}
    total = weighted = 0.0
    for (start, end), lvl in zip(pairwise(miles), segment_levels(levels)):
        length = end - start
        by_level[lvl] += length
        total += length
        weighted += length * lvl
    worst = max(levels, default=Level.LOW)
    avg = weighted / total if total > 0 else float(worst)
    return RouteSummary(
        miles_by_level={k: round(v, 2) for k, v in by_level.items()},
        avg_risk=round(avg, 3),
        max_level=worst,
    )


def _rank_key(c: Candidate) -> tuple[float, float, float, float, float]:
    s = c.summary
    return (
        round(s.miles(Level.NO_TRAVEL), 1),
        round(s.miles(Level.SEVERE), 1),
        round(s.miles(Level.HIGH), 1),
        round(s.avg_risk, 2),
        c.duration_s,
    )


def _mi(x: float) -> str:
    return f"{x:,.1f}".removesuffix(".0")


def _reason(best: Candidate, runner_up: Candidate | None) -> str:
    if runner_up is None:
        return "Only route available."
    b, o, other = _rank_key(best), _rank_key(runner_up), runner_up.route_id
    if b[0] != o[0]:
        return f"Fewest No Travel miles: {_mi(b[0])} vs {_mi(o[0])} on Route {other}."
    if b[1] != o[1]:
        return f"Fewest severe miles: {_mi(b[1])} vs {_mi(o[1])} on Route {other}."
    if b[2] != o[2]:
        return f"Fewest high-risk miles: {_mi(b[2])} vs {_mi(o[2])} on Route {other}."
    if b[3] != o[3]:
        return f"Lowest average risk: {b[3]:.2f} vs {o[3]:.2f} on Route {other}."
    minutes = round((o[4] - b[4]) / 60)
    if minutes > 0:
        return f"Same risk as Route {other}, {minutes} min faster."
    return f"Ties with Route {other} on risk and time."


def recommend(candidates: list[Candidate]) -> Recommendation:
    if not candidates:
        raise ValueError("recommend() needs at least one route")
    ordered = sorted(candidates, key=_rank_key)
    return Recommendation(
        route_id=ordered[0].route_id,
        reason=_reason(ordered[0], ordered[1] if len(ordered) > 1 else None),
        ranking=[c.route_id for c in ordered],
        all_blocked=all(c.summary.miles(Level.NO_TRAVEL) > 0 for c in candidates),
    )
