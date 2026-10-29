"""Transport-independent climate-concierge service: takes OpenAI-shaped
request dicts, returns OpenAI-shaped response dicts. The HTTP server
(server.py) is a thin wrapper; tests drive this class directly.

Flow for a user message:
  1. If the message reads like a calendar event, parse it with the
     deterministic parser and plan the climate with the rules engine.
     This path needs no LLM at all.
  2. Otherwise, if an LLM backend is configured and enabled, ask it with
     the parsed plan (or the capability brief) as context. An allowlisted
     JSON command block is validated and executed; anything else is
     returned as plain text.
  3. With no backend (ai_mode=never, or a failed backend) the capability
     blurb answers instead of an error.
"""
from __future__ import annotations

import itertools
import json
import re
import time
from datetime import datetime

from .embeddings import embed_text
from .llm import ALLOWED_COMMANDS, LlmBackend, extract_command
from .parser import parse_event
from .planner import PlanError, plan_climate

CAPABILITY_BLURB = (
    "Paste a calendar event in plain words — for example \"early flight!! "
    "leave 5ish\" — and I'll work out when to start your car's climate, "
    "what temperature to hold, and whether to re-arm Cabin Overheat "
    "Protection afterwards. No AI needed: the built-in parser and planner "
    "handle it. Connect an LLM backend (TCC_AI_BASE_URL) and I can also "
    "answer free-form questions and run climate commands by voice-style text."
)

_EVENT_HINTS = ("flight", "leave", "leaving", "depart", "drive", "trip",
                "appointment", "pickup", "pick up", "school run", "commute",
                "tomorrow", "today", "tonight", "monday", "tuesday",
                "wednesday", "thursday", "friday", "saturday", "sunday",
                "airport", "lax")
_EVENT_TIME_RE = re.compile(r"\b(am|pm|ish)\b", re.IGNORECASE)

_OUTSIDE_RE = re.compile(r"(?:outside|forecast)[^\d]{0,12}(\d{2,3})",
                         re.IGNORECASE)


def _looks_like_event(text: str) -> bool:
    low = text.lower()
    return (any(h in low for h in _EVENT_HINTS)
            or bool(_EVENT_TIME_RE.search(text))
            or bool(re.search(r"\d", text)))


class ClimateConciergeService:
    def __init__(self, settings, client_factory=None, llm_factory=None,
                 now_fn=None):
        self.settings = settings
        self.client_factory = client_factory or (lambda: None)
        self.llm_factory = llm_factory
        self.now_fn = now_fn or datetime.now
        self._ids = itertools.count(1)

    # -- plumbing ------------------------------------------------------
    def _client(self):
        return self.client_factory()

    def _llm(self):
        if self.llm_factory is not None:
            return self.llm_factory()
        if self.settings.ai_mode == "never":
            return None
        if not self.settings.ai_base_url:
            return None
        return LlmBackend(self.settings.ai_base_url, self.settings.ai_api_key,
                          self.settings.ai_model, self.settings.ai_timeout_seconds)

    def _next_id(self, prefix: str) -> str:
        return f"{prefix}-{int(time.time())}-{next(self._ids)}"

    # -- core: parse + plan -------------------------------------------
    def parse_and_plan(self, text: str, current_temp_f=None,
                       forecast_temp_f=None) -> dict:
        """Returns {"parsed": ..., "plan": ...} or {"parsed": ..., "error": ...}."""
        now = self.now_fn()
        parsed = parse_event(text, now)
        if parsed.get("temp_target_f") is None:
            parsed["temp_target_f"] = self.settings.default_temp_f
        if "temp_target_f" in parsed.get("guessed", []):
            parsed["temp_target_f"] = self.settings.default_temp_f
        if current_temp_f is None:
            m = _OUTSIDE_RE.search(text)
            if m:
                current_temp_f = float(m.group(1))
        try:
            plan = plan_climate(parsed, current_temp_f, forecast_temp_f, now)
        except PlanError as exc:
            return {"parsed": parsed, "error": str(exc)}
        return {"parsed": parsed, "plan": plan}

    def _format_plan_answer(self, result: dict) -> str:
        parsed, plan = result["parsed"], result.get("plan")
        if plan is None:
            return result["error"]
        lines = [plan["summary"], "",
                 "Parsed event (what I understood):",
                 json.dumps({k: parsed[k] for k in
                             ("departure_time", "departure_label", "destination",
                              "temp_target_f", "confidence", "guessed")},
                            indent=2)]
        if parsed["notes"]:
            lines.append("Notes: " + " ".join(parsed["notes"]))
        return "\n".join(lines)

    # -- OpenAI surface ------------------------------------------------
    def models_list(self) -> dict:
        return {"object": "list", "data": [{
            "id": self.settings.model_id,
            "object": "model",
            "created": int(time.time()),
            "owned_by": "tesla-climate-concierge",
        }]}

    def chat_completions(self, body: dict) -> dict:
        messages = body.get("messages") or []
        user_text = ""
        for m in reversed(messages):
            if m.get("role") == "user":
                user_text = str(m.get("content") or "")
                break
        if _looks_like_event(user_text):
            text = self._format_plan_answer(self.parse_and_plan(user_text))
        else:
            text = self._llm_answer(user_text)

        return {
            "id": self._next_id("chatcmpl"),
            "object": "chat.completion",
            "created": int(time.time()),
            "model": self.settings.model_id,
            "choices": [{
                "index": 0,
                "message": {"role": "assistant", "content": text},
                "finish_reason": "stop",
            }],
            "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
        }

    def embeddings(self, body: dict) -> dict:
        raw = body.get("input", "")
        texts = raw if isinstance(raw, list) else [raw]
        data = []
        for i, t in enumerate(texts):
            data.append({
                "object": "embedding",
                "index": i,
                "embedding": embed_text(str(t), self.settings.embedding_dim),
            })
        return {
            "object": "list",
            "data": data,
            "model": self.settings.model_id,
            "usage": {"prompt_tokens": 0, "total_tokens": 0},
        }

    # -- internals -----------------------------------------------------
    def _llm_answer(self, user_text: str) -> str:
        llm = self._llm()
        if llm is None:
            return CAPABILITY_BLURB
        try:
            reply = llm.chat(CAPABILITY_BLURB, user_text)
        except Exception:
            return CAPABILITY_BLURB + " (The AI backend didn't respond just now.)"
        cmd = extract_command(reply)
        if cmd is None:
            return reply
        command, vehicle_name = cmd
        vehicle = None
        needle = vehicle_name.lower()
        for v in self.settings.vehicles:
            if needle in v.name.lower() or v.name.lower() in needle:
                vehicle = v
                break
        if vehicle is None:
            names = ", ".join(v.name for v in self.settings.vehicles) or "(none yet)"
            return (f"I couldn't match \"{vehicle_name}\" to one of your cars. "
                    f"Your cars: {names}.")
        return self._execute(command, vehicle)

    def _execute(self, command: str, vehicle) -> str:
        if command not in ALLOWED_COMMANDS:
            return f"That command isn't allowed here — climate and COP actions only."
        if self.settings.dry_run:
            return (f"Dry run: would run {command} on {vehicle.name} — "
                    "nothing changed.")
        client = self._client()
        if client is None or not vehicle.vin:
            return (f"No car connected yet for {vehicle.name} — run "
                    "`tcconcierge setup`, then `tcconcierge auth`, and try again.")
        try:
            if command == "climate_start":
                client.auto_conditioning_start(vehicle.vin)
            elif command == "climate_stop":
                client.auto_conditioning_stop(vehicle.vin)
            elif command == "set_temp":
                client.set_temps(vehicle.vin, (self.settings.default_temp_f - 32) * 5 / 9)
            elif command == "cop_on":
                client.set_cabin_overheat_protection(vehicle.vin, True)
            elif command == "cop_off":
                client.set_cabin_overheat_protection(vehicle.vin, False)
            elif command == "seat_heater_on":
                client.command(vehicle.vin, "remote_seat_heater_request",
                               {"seat_id": 0, "on": True})
            elif command == "seat_heater_off":
                client.command(vehicle.vin, "remote_seat_heater_request",
                               {"seat_id": 0, "on": False})
        except Exception as exc:
            return (f"Couldn't run {command} on {vehicle.name}: {str(exc)[:150]}. "
                    "Check the car is awake and your Tesla login is still valid, "
                    "then try again.")
        return f"Done: {command} on {vehicle.name}."
