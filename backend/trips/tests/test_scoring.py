import pytest

from trips.engine.risk import Level
from trips.engine.scoring import Candidate, RouteSummary, recommend, segment_levels, summarize

L, M, H, S, N = Level.LOW, Level.MODERATE, Level.HIGH, Level.SEVERE, Level.NO_TRAVEL


def summary(nt=0.0, sev=0.0, high=0.0, avg=0.0, low=100.0):
    by = {L: low, M: 0.0, H: high, S: sev, N: nt}
    return RouteSummary(
        miles_by_level=by,
        avg_risk=avg,
        max_level=max(k for k, v in by.items() if v) if any(by.values()) else L,
    )


def test_segment_takes_worse_endpoint():
    assert segment_levels([L, H, L, L]) == [H, H, L]


def test_summarize_attributes_miles_per_segment():
    s = summarize([0, 25, 50, 60], [L, H, L, L])
    assert s.miles(H) == 50
    assert s.miles(L) == 10
    assert s.avg_risk == pytest.approx(100 / 60, abs=1e-3)
    assert s.max_level == H


def test_summarize_single_checkpoint_route():
    s = summarize([0], [M])
    assert sum(s.miles_by_level.values()) == 0
    assert s.avg_risk == 1.0


def test_fewest_severe_miles_wins_over_speed():
    rec = recommend(
        [
            Candidate("A", summary(sev=10), duration_s=100),
            Candidate("B", summary(high=50, avg=1.0), duration_s=200),
        ]
    )
    assert rec.route_id == "B"
    assert rec.ranking == ["B", "A"]
    assert rec.reason == "Fewest severe miles: 0 vs 10 on Route A."


def test_no_travel_outranks_severe():
    rec = recommend(
        [
            Candidate("A", summary(nt=5), duration_s=100),
            Candidate("B", summary(sev=30), duration_s=100),
        ]
    )
    assert rec.route_id == "B"
    assert not rec.all_blocked


def test_high_miles_break_severe_tie():
    rec = recommend(
        [
            Candidate("A", summary(high=40), duration_s=100),
            Candidate("B", summary(high=12.5), duration_s=300),
        ]
    )
    assert rec.route_id == "B"
    assert rec.reason == "Fewest high-risk miles: 12.5 vs 40 on Route A."


def test_average_risk_breaks_high_tie():
    rec = recommend(
        [
            Candidate("A", summary(avg=0.9), duration_s=100),
            Candidate("B", summary(avg=0.4), duration_s=300),
        ]
    )
    assert rec.route_id == "B"
    assert rec.reason == "Lowest average risk: 0.40 vs 0.90 on Route A."


def test_equal_risk_picks_faster():
    rec = recommend(
        [
            Candidate("A", summary(), duration_s=9000),
            Candidate("B", summary(), duration_s=7200),
        ]
    )
    assert rec.route_id == "B"
    assert rec.reason == "Same risk as Route A, 30 min faster."


def test_all_blocked_still_ranks_least_bad():
    rec = recommend(
        [
            Candidate("A", summary(nt=40), duration_s=100),
            Candidate("B", summary(nt=5), duration_s=100),
        ]
    )
    assert rec.route_id == "B"
    assert rec.all_blocked


def test_single_route():
    rec = recommend([Candidate("A", summary(), duration_s=1)])
    assert rec.reason == "Only route available."


def test_empty_candidates_raise():
    with pytest.raises(ValueError):
        recommend([])
