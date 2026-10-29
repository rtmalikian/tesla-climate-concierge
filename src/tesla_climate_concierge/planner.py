"""Weather-aware climate planning — pure, deterministic, no network.

Given a parsed calendar event plus the outside temperature (current and
forecast), decide when to start preconditioning and what else to do.
`now` is injected so tests and the simulator control time.
"""
from __future__ import annotations

from datetime import datetime, timedelta

BASE_LEAD_MINUTES = 15
TEMP_GAP_BONUS = 10        # |target - outside| >= 25°F
EXTREME_BONUS = 10         # forecast below 32°F or above 95°F
BRUTAL_BONUS = 30          # forecast at/below 0°F or at/above 110°F
MAX_LEAD_MINUTES = 60
TEMP_GAP_THRESHOLD_F = 25
SEAT_HEATER_BELOW_F = 50   # seat heater when it's this cold outside


class PlanError(Exception):
    """A human-readable planning failure — never a crash, never a traceback."""


def _fmt_12h(dt: datetime) -> str:
    return dt.strftime("%-I:%M %p")


def lead_time_minutes(temp_target_f: float, outside_temp_f: float | None) -> int:
    """Weather-aware lead time, capped at 60 minutes."""
    if outside_temp_f is None:
        return BASE_LEAD_MINUTES
    lead = BASE_LEAD_MINUTES
    if abs(temp_target_f - outside_temp_f) >= TEMP_GAP_THRESHOLD_F:
        lead += TEMP_GAP_BONUS
    if outside_temp_f < 32 or outside_temp_f > 95:
        lead += EXTREME_BONUS
    if outside_temp_f <= 0 or outside_temp_f >= 110:
        lead += BRUTAL_BONUS
    return min(lead, MAX_LEAD_MINUTES)


def plan_climate(parsed_event: dict, current_temp_f: float | None,
                 forecast_temp_f: float | None, now: datetime) -> dict:
    """Build the climate plan for one parsed event.

    Raises PlanError with a plain-English message for unusable input
    (departure in the past, no departure time at all).
    """
    dep_raw = parsed_event.get("departure_time")
    if not dep_raw:
        raise PlanError(
            "I couldn't find a departure time in that event, so I can't plan "
            "the climate yet. Try adding a time like 'leave 5:30pm' and ask again.")
    departure = datetime.fromisoformat(dep_raw)
    if departure <= now:
        raise PlanError(
            f"That departure ({_fmt_12h(departure)}) is already in the past, "
            "so there's nothing to precondition for. Add a future time — "
            "for example 'tomorrow 7am' — and I'll plan it.")
    target = parsed_event.get("temp_target_f") or 70
    outside = forecast_temp_f if forecast_temp_f is not None else current_temp_f
    lead = lead_time_minutes(target, outside)
    climate_start = departure - timedelta(minutes=lead)

    actions = [{
        "action": "climate_start",
        "at": climate_start.isoformat(),
        "at_label": _fmt_12h(climate_start),
        "description": f"Start preconditioning to {target}°F",
    }]
    if outside is not None and outside < SEAT_HEATER_BELOW_F:
        actions.append({
            "action": "seat_heater_on",
            "at": climate_start.isoformat(),
            "at_label": _fmt_12h(climate_start),
            "description": "Turn on the driver's seat heater (it's cold outside)",
        })
    actions.append({
        "action": "cop_rearm",
        "at": None,
        "at_label": "after you return",
        "description": "Re-arm Cabin Overheat Protection after the trip",
    })

    dest = parsed_event.get("destination")
    dest_txt = f" to {dest}" if dest else ""
    summary = (
        f"For your {departure.strftime('%A')} departure{dest_txt} at "
        f"{_fmt_12h(departure)}, I'll start the climate at "
        f"{_fmt_12h(climate_start)} ({lead} minutes early) and hold "
        f"{target}°F."
    )
    if outside is not None and outside < SEAT_HEATER_BELOW_F:
        summary += " Seat heater comes on too, since it's cold outside."
    summary += " Cabin Overheat Protection re-arms when you're back."

    return {
        "departure_time": departure.isoformat(),
        "departure_label": _fmt_12h(departure),
        "destination": dest,
        "temp_target_f": target,
        "lead_minutes": lead,
        "climate_start": climate_start.isoformat(),
        "climate_start_label": _fmt_12h(climate_start),
        "outside_temp_f": outside,
        "actions": actions,
        "summary": summary,
    }
