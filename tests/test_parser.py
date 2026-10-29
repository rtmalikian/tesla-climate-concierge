from datetime import datetime

from tesla_climate_concierge.parser import parse_event

NOW = datetime(2026, 10, 29, 12, 0)  # Thu noon


def test_early_flight_5ish():
    p = parse_event("early flight!! leave 5ish", NOW)
    # 5am today is past at noon -> read as tomorrow 5:00 AM
    assert p["departure_time"] == "2026-10-30T05:00:00"
    assert p["departure_label"] == "5:00 AM"
    assert p["temp_target_f"] == 70
    assert "temp_target_f" in p["guessed"]


def test_early_flight_no_time_defaults_6am():
    p = parse_event("early flight to LAX", datetime(2026, 10, 29, 20, 0))
    assert p["departure_time"] == "2026-10-30T06:00:00"
    assert "departure_time" in p["guessed"]
    assert p["destination"] == "LAX"


def test_explicit_pm_time():
    p = parse_event("dinner tomorrow 6:30pm", NOW)
    assert p["departure_time"] == "2026-10-30T18:30:00"
    assert "departure_time" not in p["guessed"]


def test_explicit_temp():
    p = parse_event("drive tomorrow 7am, set it to 72", NOW)
    assert p["temp_target_f"] == 72
    assert "temp_target_f" not in p["guessed"]


def test_warm_maps_to_72():
    p = parse_event("leave tomorrow 8am, keep it warm", NOW)
    assert p["temp_target_f"] == 72


def test_cool_maps_to_68():
    p = parse_event("leave tomorrow 8am, cool please", NOW)
    assert p["temp_target_f"] == 68


def test_missing_temp_defaults_70():
    p = parse_event("leave tomorrow 8am", NOW)
    assert p["temp_target_f"] == 70
    assert "temp_target_f" in p["guessed"]


def test_destination_after_to():
    p = parse_event("drive to Big Bear tomorrow 7am", NOW)
    assert p["destination"] == "Big Bear"


def test_tomorrow_and_weekday():
    p = parse_event("school run tomorrow 7:45am", NOW)
    assert p["departure_time"] == "2026-10-30T07:45:00"
    # 2026-10-29 is a Thursday; next Monday is 2026-11-02
    p2 = parse_event("commute Monday 8am", NOW)
    assert p2["departure_time"] == "2026-11-02T08:00:00"


def test_yesterday_is_past():
    p = parse_event("flight yesterday 5pm", NOW)
    assert p["departure_time"] == "2026-10-28T17:00:00"


def test_empty_text():
    p = parse_event("", NOW)
    assert p["departure_time"] is None
    assert p["confidence"] < 0.5


def test_no_time_at_all():
    p = parse_event("dentist appointment", NOW)
    assert p["departure_time"] is None
    assert p["destination"] == "dentist"


def test_confidence_drops_with_guesses():
    full = parse_event("drive to LAX tomorrow 5:30pm, set to 72", NOW)
    assert full["confidence"] == 1.0
    vague = parse_event("early flight", datetime(2026, 10, 29, 20, 0))
    assert vague["confidence"] < full["confidence"]
