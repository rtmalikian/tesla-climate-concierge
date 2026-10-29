# Tesla Climate Concierge — Your Tesla Preconditions Itself for What's on Your Calendar (Model 3, Model Y, Model S, Model X, Cybertruck)

**Free, open-source Tesla Fleet API app that reads your calendar events in plain words — "early flight!! leave 5ish" — and starts your car's climate at exactly the right time, at the right temperature, with Cabin Overheat Protection re-armed when you're back.**

▶ **[Try the live demo](https://rtmalikian.github.io/tesla-climate-concierge/)** — type a free-text event and watch it parse into a climate plan, no install, no car needed.

**No AI needed:** the built-in parser and weather-aware planner handle everything with zero AI involved. The optional AI layer only explains plans and accepts voice-style commands — the rules engine always computes.

## Why?

Tesla's calendar integration is **display-only**: your car shows what's on your calendar and does nothing about it. Every cold morning, owners still walk out to a freezing car, open the app, and start the climate by hand — or forget entirely and drive the first ten minutes shivering. Meanwhile your calendar already knows when you leave.

- **"Early flight, leave 5ish" actually works** — paste free-text events and the concierge understands them: departure time (including "5ish", "5:30pm", "early flight" → 6:00 AM), destination hints ("to LAX", "Big Bear"), and temperature targets ("warm" → 72°F, "cool" → 68°F, or your exact degrees)
- **Weather-aware lead times** — base 15 minutes before departure, longer when it's brutally cold or hot outside (up to 60 minutes), so the cabin is actually at temperature when you open the door
- **Seat heater when it's cold, COP re-armed when you're back** — the plan covers the whole trip, not just the departure
- **Plain-English preview first** — `tcconcierge preview "early flight!! leave 5ish"` shows exactly what would happen before anything touches your car
- **AI endpoints included** — an OpenAI-compatible server (`/v1/chat/completions`, `/v1/models`, `/v1/embeddings`) so any AI client can ask about plans or run climate commands; LLM-proposed commands are validated against a climate/COP-only allowlist, and dry-run is honored
- **Privacy by architecture** — vehicle data is sent **only** to the backend *you* configure. With `TCC_AI_MODE=never` (or no backend), nothing leaves your machine except Tesla API calls

## How it works

```
  8:00 PM  You paste "early flight!! leave 5ish to LAX"
           → parsed: depart 5:00 AM, destination LAX, target 70°F
  4:45 AM  Outside 48°F → 15-minute lead → climate starts, seat heater on
  5:00 AM  You step into a warm car at 70°F and drive to LAX
  later    Cabin Overheat Protection re-arms automatically while parked
```

**Expected API cost:** ~$0.10–0.30/month at the default schedule — a couple of commands and one data call per trip, no wake-ups, no polling. The simulator prints its own estimate (`tcconcierge simulate`).

## Quickstart (for owners, not developers)

```bash
git clone https://github.com/rtmalikian/tesla-climate-concierge.git
cd tesla-climate-concierge
python3 -m venv .venv && .venv/bin/pip install -e .
tcconcierge setup      # plain-language questions — writes .env for you
tcconcierge simulate   # see a demo with pretend cars and events
tcconcierge preview "early flight!! leave 5ish"   # dry-run a real plan
tcconcierge auth       # sign in to Tesla once (opens a link)
tcconcierge serve      # start the AI chat server on port 8643
```

What you'll see when it works: `simulate` prints a timeline of four pretend events with parsed departures, climate-start times, and an "ALL OK" invariant line. `preview` prints a plain-English plan and the exact actions, changing nothing.

## Tesla developer setup

1. Create a free app at [developer.tesla.com](https://developer.tesla.com) (sign in → Create App) and note the Client ID and Client Secret — `tcconcierge setup` asks for them in plain words.
2. Scopes needed: `openid offline_access vehicle_device_data vehicle_cmds`.
3. Run `tcconcierge auth`, open the link, sign in, and pair the virtual key as described at <https://developer.tesla.com/docs/fleet-api#pairing>.

## `.env` reference

| Variable | Meaning | Default |
|---|---|---|
| `TESLA_CLIENT_ID` / `TESLA_CLIENT_SECRET` | Your Tesla developer app credentials | — |
| `TESLA_REGION` | `na`, `eu`, or `cn` | `na` |
| `TCC_VEHICLES` | Cars as `nickname=VIN` pairs (nickname alone is fine) | — |
| `TCC_SERVER_HOST` / `TCC_SERVER_PORT` | Chat server address | `127.0.0.1` / `8643` |
| `TCC_SERVER_API_KEY` | Optional password for the chat server (blank = none) | — |
| `TCC_AI_BASE_URL` / `TCC_AI_API_KEY` / `TCC_AI_MODEL` | Pluggable LLM backend (any OpenAI-compatible API) | Ollama `http://localhost:11434/v1` / — / `llama3.1` |
| `TCC_AI_MODE` | `auto`, `always`, or `never` (never = no AI at all) | `auto` |
| `TCC_DEFAULT_TEMP_F` | Cabin target when an event gives no temperature | `70` |
| `TCC_COP_REARM` | Re-arm Cabin Overheat Protection after trips (`1`/`0`) | `1` |
| `TCC_DRY_RUN` | Preview commands instead of running them (`1`/`0`) | `0` |

## AI endpoints

The server speaks the OpenAI API, so any OpenAI-compatible client works. Streaming is not supported (`stream=true` is ignored). Vehicle data goes only to your configured backend.

```bash
# What models are available?
curl http://127.0.0.1:8643/v1/models

# Parse an event and plan the climate (works with no AI backend at all)
curl http://127.0.0.1:8643/v1/chat/completions -H 'Content-Type: application/json' -d '{
  "model": "tesla-climate-concierge",
  "messages": [{"role": "user", "content": "early flight!! leave 5ish to LAX"}]
}'

# Embeddings (deterministic local hashing vectors, dim 384)
curl http://127.0.0.1:8643/v1/embeddings -H 'Content-Type: application/json' -d '{
  "input": "early flight to LAX"
}'
```

With a bearer key set (`TCC_SERVER_API_KEY`), add `-H "Authorization: Bearer <key>"` to every call.

## FAQ

**Does my Tesla really precondition itself from my calendar?**
Not on its own — Tesla's calendar view is display-only. This app closes that gap: it parses your events and issues the Fleet API climate commands at the right time.

**Do I need AI for this to work?**
No. The parser and planner are deterministic rules that fully work with the AI backend off (`TCC_AI_MODE=never`). AI only adds free-form explanations and voice-style commands.

**What does "leave 5ish" become?**
With an early/flight context, 5:00 AM; on its own, 5:00 PM. "Early flight" with no time defaults to 6:00 AM. Every guess is reported back in the parsed output, with a confidence score.

**How does the weather change the start time?**
Base lead is 15 minutes. It grows by 10 minutes when the gap between your target and the outside temperature is 25°F or more, and by 10 more in extreme cold (below 32°F) or heat (above 95°F), capped at 60 minutes.

**What if my departure time is in the past?**
You get a plain-English message ("That departure is already in the past…") — never a crash or a stack trace.

**Does it wake my car to check things?**
No. Planning needs no car reads at all, and commands only go out at climate-start time. Wakes are the priciest Fleet API call, so the app never spends one just to measure something.

**Is my car data sent to anyone?**
Only to the LLM backend you configure (`TCC_AI_BASE_URL`). With no backend configured, nothing leaves your machine except Tesla API calls.

## License

MIT — Raphael Malikian <rtmalikian@gmail.com>. Free and open source; part of a Tesla Fleet API app series for Model 3, Model Y, Model S, Model X, and Cybertruck owners.
