"""Free-text calendar-event parsing — pure, deterministic, no network.

Turns owner shorthand like "early flight!! leave 5ish" into structured
data: a departure time, a destination hint, and a cabin temperature
target. This is the regex fallback AND the reference implementation: it
fully works with the LLM backend off. When an LLM is configured, the
service layer may ask it to parse first and falls back to this module
whenever the LLM answer is missing or malformed.

`now` is always injected so tests (and the simulator) control time.
"""
from __future__ import annotations

import re
from datetime import datetime, time, timedelta

# ---------------------------------------------------------------------------
# Time words
# ---------------------------------------------------------------------------

_TIME_12H_RE = re.compile(
    r"\b(\d{1,2})(?::(\d{2}))?\s*(am|pm|a\.m\.|p\.m\.)\b", re.IGNORECASE)
_TIME_ISH_RE = re.compile(r"\b(\d{1,2})(?::(\d{2}))?\s*ish\b", re.IGNORECASE)
_TIME_24H_RE = re.compile(r"\b([01]?\d|2[0-3]):([0-5]\d)\b")
_TIME_BARE_RE = re.compile(r"\bleave\s+(?:at\s+|around\s+)?(\d{1,2})(?::(\d{2}))?\b",
                           re.IGNORECASE)

_WEEKDAYS = {"monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3,
             "friday": 4, "saturday": 5, "sunday": 6}
_MONTHS = {"jan": 1, "january": 1, "feb": 2, "february": 2, "mar": 3,
           "march": 3, "apr": 4, "april": 4, "may": 5, "jun": 6, "june": 6,
           "jul": 7, "july": 7, "aug": 8, "august": 8, "sep": 9, "sept": 9,
           "september": 9, "oct": 10, "october": 10, "nov": 11, "november": 11,
           "dec": 12, "december": 12}

_EARLY_WORDS = ("early", "morning", "flight", "airport", "sunrise", "dawn")
_EVENING_WORDS = ("evening", "dinner", "night", "sunset", "late")

# ---------------------------------------------------------------------------
# Destination + temperature
# ---------------------------------------------------------------------------

_KNOWN_PLACES = (
    "lax", "airport", "work", "office", "gym", "school", "church", "beach",
    "big bear", "mammoth", "vegas", "san diego", "downtown", "home",
    "doctor", "dentist", "costco", "target", "mall", "park", "lake",
)

_TEMP_EXPLICIT_RE = re.compile(
    r"\b(\d{2,3})\s*(?:°|degrees?|deg|f\b)?", re.IGNORECASE)
_TEMP_WORDS = {"warm": 72, "cozy": 72, "toasty": 72, "hot": 74, "cold": 74,
               "freezing": 74, "chilly": 68, "cool": 68, "mild": 70}

_DEFAULT_TEMP_F = 70
_EARLY_FLIGHT_DEFAULT = time(6, 0)   # "early flight" with no time -> 6:00 AM


def _next_weekday(now: datetime, target: int) -> datetime:
    delta = (target - now.weekday()) % 7
    return now + timedelta(days=delta or 7)


def _resolve_day(text: str, now: datetime) -> tuple[datetime, bool]:
    """Return (day base datetime, day_was_explicit)."""
    low = text.lower()
    if "tomorrow" in low or "tmw" in low:
        return now + timedelta(days=1), True
    if "yesterday" in low:
        return now - timedelta(days=1), True
    if "today" in low or "tonight" in low:
        return now, True
    for name, num in _WEEKDAYS.items():
        if re.search(rf"\b{name}\b", low):
            return _next_weekday(now, num), True
    m = re.search(r"\b(\d{1,2})/(\d{1,2})(?:/(\d{2,4}))?\b", text)
    if m:
        month, day = int(m.group(1)), int(m.group(2))
        year = int(m.group(3)) if m.group(3) else now.year
        if year < 100:
            year += 2000
        try:
            return now.replace(year=year, month=month, day=day), True
        except ValueError:
            pass
    m = re.search(r"\b([a-z]+)\s+(\d{1,2})(?:st|nd|rd|th)?\b", low)
    if m and m.group(1) in _MONTHS:
        try:
            return now.replace(month=_MONTHS[m.group(1)], day=int(m.group(2))), True
        except ValueError:
            pass
    return now, False


def _parse_clock(text: str, now: datetime) -> tuple[time | None, bool, str]:
    """Return (clock time, was_explicit, note)."""
    low = text.lower()
    m = _TIME_12H_RE.search(text)
    if m:
        hour, minute = int(m.group(1)), int(m.group(2) or 0)
        pm = m.group(3).lower().startswith("p")
        if pm and hour != 12:
            hour += 12
        if not pm and hour == 12:
            hour = 0
        if hour > 23:
            return None, False, ""
        return time(hour, minute), True, ""
    m = _TIME_ISH_RE.search(text)
    if m:
        hour, minute = int(m.group(1)), int(m.group(2) or 0)
        if any(w in low for w in _EARLY_WORDS):
            pass  # early context -> AM
        elif any(w in low for w in _EVENING_WORDS):
            if hour != 12:
                hour += 12
        else:
            # No context: "5ish" on its own reads as afternoon/evening.
            if 1 <= hour <= 6:
                hour += 12
        if hour == 24:
            hour = 0
        return time(hour, minute), True, "time read as approximate ('ish')"
    m = _TIME_24H_RE.search(text)
    if m and ("leave" in low or "depart" in low or ":" in text):
        hour, minute = int(m.group(1)), int(m.group(2))
        return time(hour, minute), True, ""
    m = _TIME_BARE_RE.search(text)
    if m:
        hour, minute = int(m.group(1)), int(m.group(2) or 0)
        if any(w in low for w in _EARLY_WORDS):
            pass
        elif any(w in low for w in _EVENING_WORDS):
            if hour != 12:
                hour += 12
        elif 1 <= hour <= 6:
            hour += 12
        return time(hour, minute), True, "time read as approximate (no am/pm given)"
    if "noon" in low:
        return time(12, 0), True, ""
    if "midnight" in low:
        return time(0, 0), True, ""
    if any(w in low for w in _EARLY_WORDS):
        return _EARLY_FLIGHT_DEFAULT, False, (
            "no time given — 'early' events default to 6:00 AM")
    return None, False, ""


def _parse_destination(text: str) -> tuple[str | None, bool]:
    low = text.lower()
    for place in _KNOWN_PLACES:
        if re.search(rf"\b{re.escape(place)}\b", low):
            # Return the place in the owner's own casing where possible.
            m = re.search(rf"\b({re.escape(place)})\b", text, re.IGNORECASE)
            return (m.group(1) if m else place), False
    m = re.search(
        r"\b(?:to|for|at)\s+([A-Za-z][A-Za-z' ]{1,40}?)"
        r"(?=\s+(?:at|leave|leaving|depart|departure|by|for|—|-|,)|$)",
        text)
    if m:
        dest = m.group(1).strip()
        # Strip trailing time/temp words the phrase may have swallowed.
        dest = re.sub(r"\s+(?:around|about|at)\s+\d.*$", "", dest).strip()
        dest = re.sub(r"\s+\d+\s*(?:degrees?|°|f)?$", "", dest,
                      flags=re.IGNORECASE).strip()
        if dest and dest.lower() not in ("the", "a", "work"):
            return dest, False
    return None, True


def _parse_temp(text: str) -> tuple[int, str, str]:
    """Explicit degrees win; feeling words map to targets; else default.

    Returns (temp, source, note) with source in explicit|word|default.
    Only 'default' counts as guessed — a word mapping is an informed
    inference from the owner's own words, not a blind default.
    """
    m = re.search(r"\b(\d{2,3})\s*(?:°|degrees?|deg)\b", text, re.IGNORECASE)
    if m and 50 <= int(m.group(1)) <= 85:
        return int(m.group(1)), "explicit", ""
    m = re.search(r"\b(?:temp|temperature|set(?: it)?(?: to)?)\s+(\d{2,3})\b",
                  text, re.IGNORECASE)
    if m and 50 <= int(m.group(1)) <= 85:
        return int(m.group(1)), "explicit", ""
    low = text.lower()
    for word, temp in _TEMP_WORDS.items():
        if re.search(rf"\b{word}\b", low):
            return temp, "word", f"no degrees given — '{word}' mapped to {temp}°F"
    return _DEFAULT_TEMP_F, "default", "no temperature given — default 70°F"


def _fmt_12h(dt: datetime) -> str:
    return dt.strftime("%-I:%M %p") if hasattr(dt, "strftime") else str(dt)


def parse_event(text: str, now: datetime) -> dict:
    """Parse free-text calendar event -> structured dict.

    Keys: raw_text, departure_time (ISO), departure_label (12-hour words),
    destination (str|None), temp_target_f, confidence (0..1), guessed
    (field names that were defaulted), notes (plain-English explanations).
    departure_time is None only when no day/time cue exists at all.
    """
    if not text or not text.strip():
        return {"raw_text": text, "departure_time": None, "departure_label": None,
                "destination": None, "temp_target_f": _DEFAULT_TEMP_F,
                "confidence": 0.1, "guessed": ["departure_time", "temp_target_f"],
                "notes": ["Empty event text — nothing to parse."]}
    day, day_explicit = _resolve_day(text, now)
    clock, clock_explicit, clock_note = _parse_clock(text, now)
    destination, dest_guessed = _parse_destination(text)
    temp, temp_source, temp_note = _parse_temp(text)

    guessed, notes = [], []
    if clock is None:
        departure = None
        guessed.append("departure_time")
        notes.append("No departure time found in the event text.")
    else:
        departure = datetime.combine(day.date(), clock)
        if not clock_explicit:
            guessed.append("departure_time")
            notes.append(clock_note)
        elif clock_note:
            notes.append(clock_note)
        if not day_explicit and departure <= now:
            # A bare time already past today almost always means tomorrow.
            departure = departure + timedelta(days=1)
            notes.append("That time already passed today, so I read it as tomorrow.")
    if temp_source == "default":
        guessed.append("temp_target_f")
        notes.append(temp_note)
    elif temp_note:
        notes.append(temp_note)
    if dest_guessed:
        guessed.append("destination")
        notes.append("No destination found — climate plan has no destination hint.")

    confidence = 1.0 - 0.25 * ("departure_time" in guessed) \
        - 0.15 * ("temp_target_f" in guessed) \
        - 0.10 * ("destination" in guessed)
    confidence = round(max(0.1, min(1.0, confidence)), 2)

    return {
        "raw_text": text,
        "departure_time": departure.isoformat() if departure else None,
        "departure_label": _fmt_12h(departure) if departure else None,
        "destination": destination,
        "temp_target_f": temp,
        "confidence": confidence,
        "guessed": guessed,
        "notes": notes,
    }
