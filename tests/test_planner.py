from datetime import datetime

import pytest

from tesla_climate_concierge.parser import parse_event
from tesla_climate_concierge.planner import PlanError, lead_time_minutes, plan_climate

NOW = datetime(2026, 10, 29, 12, 0)


def _plan(text, current, forecast, now=NOW):
    return plan_climate(parse_event(text, now), current, forecast, now)


def test_base_lead_15():
    plan = _plan("leave tomorrow 8am", 65, 65)
    assert plan["lead_minutes"] == 15
    assert plan["climate_start"] == "2026-10-30T07:45:00"


def test_temp_gap_adds_10():
    plan = _plan("leave tomorrow 8am", 40, 40)  # target 70, gap 30
    assert plan["lead_minutes"] == 25


def test_extreme_forecast_adds_10():
    plan = _plan("leave tomorrow 8am", 65, 20)  # below 32F
    assert plan["lead_minutes"] == 35  # gap 50 -> +10, extreme -> +10


def test_extreme_heat():
    plan = _plan("leave tomorrow 8am", 65, 100)  # above 95F
    assert plan["lead_minutes"] == 35


def test_lead_capped_at_60():
    assert lead_time_minutes(70, -10) == 60  # gap + extreme + brutal, capped
    assert lead_time_minutes(70, 115) == 60


def test_seat_heater_when_cold():
    plan = _plan("leave tomorrow 8am", 40, 40)
    actions = [a["action"] for a in plan["actions"]]
    assert "seat_heater_on" in actions


def test_no_seat_heater_when_mild():
    plan = _plan("leave tomorrow 8am", 65, 65)
    actions = [a["action"] for a in plan["actions"]]
    assert "seat_heater_on" not in actions


def test_cop_rearm_always_present():
    plan = _plan("leave tomorrow 8am", 65, 65)
    assert "cop_rearm" in [a["action"] for a in plan["actions"]]
    assert "Cabin Overheat Protection" in plan["summary"]


def test_summary_is_plain_english():
    plan = _plan("drive to LAX tomorrow 5:30pm, set to 72", 65, 65)
    assert "5:30 PM" in plan["summary"]
    assert "LAX" in plan["summary"]
    assert "72°F" in plan["summary"]


def test_past_departure_plain_english_error():
    with pytest.raises(PlanError) as exc:
        _plan("flight yesterday 5pm", 65, 65)
    assert "already in the past" in str(exc.value)
    assert "Traceback" not in str(exc.value)


def test_missing_departure_plain_english_error():
    with pytest.raises(PlanError) as exc:
        _plan("dentist appointment", 65, 65)
    assert "departure time" in str(exc.value)


def test_missing_outside_temp_uses_base_lead():
    plan = _plan("leave tomorrow 8am", None, None)
    assert plan["lead_minutes"] == 15
    assert plan["outside_temp_f"] is None
