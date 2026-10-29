"""End-to-end: the demo timeline asserts the core invariant — for every
event, the climate starts within the weather-aware lead window before
departure (never late, never more than the capped lead early)."""
from datetime import datetime

from tesla_climate_concierge.simulator import run_demo


def test_core_invariant_all_events():
    report = run_demo()
    assert report["all_invariants_ok"] is True
    assert len(report["events"]) == 4
    for e in report["events"]:
        dep = datetime.fromisoformat(e["plan"]["departure_time"])
        start = datetime.fromisoformat(e["plan"]["climate_start"])
        lead = (dep - start).total_seconds() / 60
        assert 0 < lead <= 60
        assert lead == e["plan"]["lead_minutes"]


def test_cold_trip_gets_longer_lead():
    report = run_demo()
    big_bear = next(e for e in report["events"] if "Big Bear" in e["text"])
    mild = next(e for e in report["events"] if "dentist" in e["text"])
    assert big_bear["plan"]["lead_minutes"] > mild["plan"]["lead_minutes"]
    assert "seat_heater_on" in [a["action"] for a in big_bear["plan"]["actions"]]


def test_cost_line_present():
    report = run_demo()
    assert report["commands_per_day"] > 0
    assert report["estimated_monthly_cost_usd"] < 1.0
