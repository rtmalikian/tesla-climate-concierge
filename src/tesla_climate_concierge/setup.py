"""Guided first-run setup: plain-language questions, writes .env itself.

Built for Tesla owners, not developers — defaults everywhere, numbered
choices, times in 12-hour words, and cars picked by nickname (a VIN is
optional and can be added later at pairing time). Testable: input and
output are injectable.
"""
from __future__ import annotations

import os
from pathlib import Path


def _ask(input_fn, out, prompt: str, default: str = "") -> str:
    suffix = f" [{default}]" if default else ""
    out(f"{prompt}{suffix}")
    answer = input_fn("> ").strip()
    return answer or default


def _ask_required(input_fn, out, prompt: str, help_text: str) -> str:
    while True:
        out(help_text)
        answer = input_fn(f"{prompt} ").strip()
        if answer:
            return answer
        out("That one's required — without it the app can't talk to your car.")


def run_setup(input_fn=input, out=print, env_path: str = ".env") -> Path:
    out("")
    out("Welcome to Tesla Climate Concierge setup — I'll ask a few questions")
    out("and write the settings file for you. Press Enter to accept a [default].")
    out("")

    path = Path(env_path)
    if path.exists():
        again = _ask(input_fn, out,
                     "A settings file (.env) already exists. Replace it? (y/n)", "n")
        if again.lower() not in ("y", "yes"):
            out("Keeping your existing settings. Nothing changed.")
            return path

    out("STEP 1 of 5 — Connect to Tesla")
    out("Create a free developer app at developer.tesla.com (sign in, then")
    out("'Create App'). Tesla will show you a Client ID and Client Secret.")
    client_id = _ask_required(input_fn, out, "Paste your Client ID:",
                              "First, the Client ID:")
    client_secret = _ask_required(input_fn, out, "Paste your Client Secret:",
                                  "Now the Client Secret (it stays on this computer):")

    out("")
    out("STEP 2 of 5 — Your cars")
    out("For each car, just a nickname (like Model Y). A VIN is optional —")
    out("find it in your Tesla app under Controls → Software, or leave it")
    out("blank and add it when you pair the car.")
    vehicles: list[tuple[str, str]] = []
    while True:
        n = len(vehicles) + 1
        name = _ask(input_fn, out,
                    f"Car {n} nickname (e.g. Model Y) — or press Enter if done:",
                    "" if vehicles else "")
        if not name:
            if vehicles:
                break
            out("Add at least one car to continue.")
            continue
        vin = _ask(input_fn, out, f"VIN for {name} (blank is fine):")
        vehicles.append((name, vin))

    out("")
    out("STEP 3 of 5 — Your comfort defaults")
    out("When a calendar event doesn't say a temperature, what should the")
    out("car aim for? Most owners pick 70°F.")
    default_temp = _ask(input_fn, out,
                        "Default cabin temperature in °F:", "70")
    out("After a trip, should Cabin Overheat Protection switch back on")
    out("automatically? (It keeps the cabin from baking while parked.)")
    out("  1) Yes — re-arm it after every trip (default)")
    out("  2) No — leave it as it was")
    cop_choice = _ask(input_fn, out, "Pick 1 or 2:", "1")
    cop_rearm = "1" if cop_choice != "2" else "0"

    out("")
    out("STEP 4 of 5 — The AI brain (optional)")
    out("  1) Built-in answers only — no AI, nothing leaves this computer")
    out("  2) Ollama on this computer — free local AI (default)")
    out("  3) Another AI service (OpenAI, Groq, LM Studio…) — you'll paste its details")
    choice = _ask(input_fn, out, "Pick 1, 2 or 3:", "2")
    ai_mode, ai_url, ai_key, ai_model = "auto", "http://localhost:11434/v1", "", "llama3.1"
    if choice == "1":
        ai_mode = "never"
    elif choice == "3":
        ai_url = _ask_required(input_fn, out, "Service address (base URL):",
                               "Paste the service's API address:")
        ai_key = _ask(input_fn, out, "API key for that service (stored only here):")
        ai_model = _ask(input_fn, out, "Model name:", "gpt-4o-mini")

    out("")
    out("STEP 5 of 5 — The chat server")
    port = _ask(input_fn, out, "Port for the chat address:", "8643")
    server_key = _ask(input_fn, out,
                      "Optional password for the chat address (blank = none):")

    lines = [
        "# Written by `tcconcierge setup` — edit by re-running setup any time.",
        f"TESLA_CLIENT_ID={client_id}",
        f"TESLA_CLIENT_SECRET={client_secret}",
        "TESLA_REGION=na",
        "TESLA_REDIRECT_URI=http://localhost:8080/callback",
        "TCC_VEHICLES=" + ",".join(f"{name}={vin}" for name, vin in vehicles),
        "TCC_SERVER_HOST=127.0.0.1",
        f"TCC_SERVER_PORT={port}",
        f"TCC_SERVER_API_KEY={server_key}",
        "TCC_MODEL_ID=tesla-climate-concierge",
        f"TCC_AI_BASE_URL={ai_url}",
        f"TCC_AI_API_KEY={ai_key}",
        f"TCC_AI_MODEL={ai_model}",
        f"TCC_AI_MODE={ai_mode}",
        "TCC_AI_TIMEOUT_SECONDS=20",
        "TCC_EMBEDDING_DIM=384",
        "TCC_TOKEN_FILE=~/.tcc/tokens.json",
        "TCC_DRY_RUN=0",
        f"TCC_DEFAULT_TEMP_F={default_temp}",
        f"TCC_COP_REARM={cop_rearm}",
    ]
    path.write_text("\n".join(lines) + "\n")
    os.chmod(path, 0o600)

    out("")
    out("All set — settings saved to .env (only readable by you).")
    out("Next steps:")
    out("  1) tcconcierge auth       — sign in to Tesla once (opens a link)")
    out("  2) tcconcierge simulate   — see a demo with pretend cars and events")
    out("  3) tcconcierge serve      — start the AI chat server")
    out("  4) tcconcierge preview \"early flight!! leave 5ish\" — dry-run a plan")
    return path
