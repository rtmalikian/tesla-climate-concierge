"""CLI: tcconcierge setup | auth | serve | parse | preview | simulate"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from datetime import datetime

from .config import ConfigError, load_settings

__version__ = "0.1.0"


def _setup_logging(verbose: bool) -> None:
    logging.basicConfig(level=logging.DEBUG if verbose else logging.INFO,
                        format="%(levelname)s %(name)s: %(message)s")


def _client(settings):
    from .tesla_client import TeslaClient
    return TeslaClient(settings.client_id, settings.client_secret,
                       region=settings.region, redirect_uri=settings.redirect_uri,
                       token_file=settings.token_file)


def cmd_auth(args, settings) -> int:
    client = _client(settings)
    print("Open this URL in your browser and authorize:")
    print(client.authorize_url())
    print("Virtual-key pairing: https://developer.tesla.com/docs/fleet-api#pairing")
    return 0


def cmd_setup(args, settings) -> int:
    from .setup import run_setup
    run_setup()
    return 0


def cmd_serve(args, settings) -> int:
    from .server import serve
    from .service import ClimateConciergeService

    def client_factory():
        return _client(settings)

    service = ClimateConciergeService(settings, client_factory=client_factory)
    print("Vehicle data goes ONLY to your configured LLM backend "
          f"(TCC_AI_BASE_URL={settings.ai_base_url or 'none'}); "
          "the parser and planner work with no backend at all.")
    serve(service)
    return 0


def _service(settings):
    from .service import ClimateConciergeService
    return ClimateConciergeService(settings)


def cmd_parse(args, settings) -> int:
    service = _service(settings)
    result = service.parse_and_plan(args.event)
    print(json.dumps(result, indent=2))
    return 0


def cmd_preview(args, settings) -> int:
    """Plain-English dry run: what WOULD happen, before anything real."""
    from .planner import PlanError
    service = _service(settings)
    result = service.parse_and_plan(args.event)
    if "error" in result:
        print(f"Couldn't plan that yet: {result['error']}")
        return 1
    plan, parsed = result["plan"], result["parsed"]
    print("PREVIEW — nothing has been changed on your car.")
    print("")
    print(plan["summary"])
    print("")
    print("What would happen, in order:")
    for a in plan["actions"]:
        print(f"  • {a['at_label']}: {a['description']}")
    if parsed["notes"]:
        print("")
        print("How I read your event: " + " ".join(parsed["notes"]))
    print("")
    print("To run this for real, use: tcconcierge serve (AI chat) or wait "
          "for the scheduled run — it asks for confirmation first.")
    return 0


def cmd_simulate(_args, settings) -> int:
    from .simulator import render_demo, run_demo
    print(render_demo(run_demo(settings)))
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="tcconcierge",
        description="Your Tesla's climate, planned from your calendar in plain words.")
    p.add_argument("--version", action="version", version=f"tcconcierge {__version__}")
    p.add_argument("--env-file", default=None)
    p.add_argument("-v", "--verbose", action="store_true")
    sub = p.add_subparsers(dest="command", required=True)
    sub.add_parser("setup", help="Guided first-run setup (plain-language questions)")
    sub.add_parser("auth", help="Authorize with your Tesla account (one-time)")
    sub.add_parser("serve", help="Run the OpenAI-compatible API server")
    parse_p = sub.add_parser("parse", help="Parse an event and show the JSON + plan")
    parse_p.add_argument("event", help='e.g. "early flight!! leave 5ish"')
    prev_p = sub.add_parser("preview", help="Plain-English dry run of a plan (changes nothing)")
    prev_p.add_argument("event", help='e.g. "early flight!! leave 5ish"')
    sub.add_parser("simulate", help="Demo timeline with pretend cars/events (no API calls)")
    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    _setup_logging(args.verbose)
    env = dict(os.environ)
    if args.env_file:
        from dotenv import load_dotenv
        load_dotenv(args.env_file, override=True)
        env = dict(os.environ)
    else:
        from dotenv import load_dotenv
        load_dotenv(override=False)
        env = dict(os.environ)
    try:
        settings = load_settings(env)
    except ConfigError as exc:
        print(f"Config error: {exc}", file=sys.stderr)
        return 2
    handlers = {"setup": cmd_setup, "auth": cmd_auth, "serve": cmd_serve,
                "parse": cmd_parse, "preview": cmd_preview,
                "simulate": cmd_simulate}
    try:
        return handlers[args.command](args, settings)
    except Exception as exc:  # human error messages, never a stack trace
        print(f"Something went wrong: {exc}. Check your settings with "
              "`tcconcierge setup`, then try again.", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
