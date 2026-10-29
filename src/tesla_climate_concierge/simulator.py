"""Fake fleet + fake calendar events over virtual time. No API calls,
no real cars, no credentials, no network.

The demo proves the core invariant: for every event, the climate starts
inside the weather-aware lead window before departure — never late, never
more than the capped lead early.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timedelta

from .config import VehicleConfig
from .planner import plan_climate
from .parser import parse_event

# Community-reported Fleet API rates (playbook §6): ~$1 per 1,000 commands,
# ~$1 per 500 data calls, ~$1 per 50 wake-ups. The concierge never wakes a
# sleeping car to plan — it only issues commands at climate-start time.
COMMAND_COST = 1 / 1000
DATA_CALL_COST = 1 / 500

# (event text, current °F, forecast °F) — a plausible owner day.
DEMO_EVENTS = [
    ("early flight!! leave 5ish to LAX", 52, 48),
    ("dentist appointment tomorrow 9:30am, keep it warm", 61, 60),
    ("drive to Big Bear tomorrow 7am, it's freezing", 28, 22),
    ("dinner with friends tomorrow 6:30pm, cool please", 78, 80),
]

# Virtual "now": the evening before the demo day, so every event is future.
DEMO_NOW = datetime(2026, 10, 29, 20, 0)


@dataclass
class FakeVehicle:
    vin: str
    name: str
    climate_on: bool = False


class FakeTeslaClient:
    """Stand-in for TeslaClient with the climate methods the service uses."""

    def __init__(self, vehicles: list[FakeVehicle]):
        self.vehicles = {v.vin: v for v in vehicles}
        self.command_log: list[tuple[str, str]] = []

    def auto_conditioning_start(self, vin: str) -> dict:
        self.vehicles[vin].climate_on = True
        self.command_log.append(("auto_conditioning_start", vin))
        return {"result": True}

    def auto_conditioning_stop(self, vin: str) -> dict:
        self.vehicles[vin].climate_on = False
        self.command_log.append(("auto_conditioning_stop", vin))
        return {"result": True}

    def set_temps(self, vin: str, temp_c: float) -> dict:
        self.command_log.append(("set_temps", vin))
        return {"result": True}

    def set_cabin_overheat_protection(self, vin: str, on: bool) -> dict:
        self.command_log.append(("set_cabin_overheat_protection", vin))
        return {"result": True}

    def command(self, vin: str, name: str, data: dict | None = None) -> dict:
        self.command_log.append((name, vin))
        return {"result": True}


def demo_vehicles() -> list[FakeVehicle]:
    return [FakeVehicle(vin="VINY", name="Model Y")]


def run_demo(settings=None, now: datetime = DEMO_NOW) -> dict:
    """Run every demo event through the real parser + planner and build
    the virtual timeline. Returns a report dict the CLI prints and tests
    assert on."""
    events = []
    commands = data_calls = 0
    for text, current_f, forecast_f in DEMO_EVENTS:
        parsed = parse_event(text, now)
        plan = plan_climate(parsed, current_f, forecast_f, now)
        dep = datetime.fromisoformat(plan["departure_time"])
        start = datetime.fromisoformat(plan["climate_start"])
        lead = (dep - start).total_seconds() / 60
        events.append({
            "text": text, "parsed": parsed, "plan": plan,
            "lead_minutes_actual": lead,
            "invariant_ok": 0 < lead <= 60 and lead == plan["lead_minutes"],
        })
        commands += 2  # climate_start + COP re-arm
        data_calls += 1
    daily_cost = commands * COMMAND_COST + data_calls * DATA_CALL_COST
    return {
        "now": now.isoformat(),
        "events": events,
        "commands_per_day": commands,
        "data_calls_per_day": data_calls,
        "estimated_daily_cost_usd": round(daily_cost, 4),
        "estimated_monthly_cost_usd": round(daily_cost * 30, 2),
        "all_invariants_ok": all(e["invariant_ok"] for e in events),
    }


def render_demo(report: dict) -> str:
    lines = [f"Virtual now: {report['now']}", ""]
    for e in report["events"]:
        p, plan = e["parsed"], e["plan"]
        lines.append(f"Event: {e['text']!r}")
        lines.append(f"  parsed: departure {p['departure_label']}, "
                     f"destination {p['destination'] or '(none)'}, "
                     f"target {p['temp_target_f']}°F, "
                     f"confidence {p['confidence']}")
        lines.append(f"  plan:   climate starts {plan['climate_start_label']} "
                     f"({plan['lead_minutes']} min before departure), "
                     f"outside {plan['outside_temp_f']}°F")
        lines.append(f"  actions: {', '.join(a['action'] for a in plan['actions'])}")
        lines.append(f"  invariant (climate starts within the lead window "
                     f"before departure): {'OK' if e['invariant_ok'] else 'FAIL'}")
        lines.append("")
    lines.append(f"API calls per day: {report['commands_per_day']} commands + "
                 f"{report['data_calls_per_day']} data calls (no wake-ups)")
    lines.append(f"Estimated API cost: ${report['estimated_daily_cost_usd']:.4f}/day, "
                 f"~${report['estimated_monthly_cost_usd']:.2f}/month")
    lines.append(f"Core invariant: {'ALL OK' if report['all_invariants_ok'] else 'FAILED'}")
    return "\n".join(lines)
