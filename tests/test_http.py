"""Real HTTP smoke test: the stdlib server on an ephemeral port must
serve all three OpenAI-compatible endpoints with the right shapes."""
import json
import threading
import urllib.request
from http.server import ThreadingHTTPServer

from tesla_climate_concierge.config import Settings, VehicleConfig
from tesla_climate_concierge.server import make_handler
from tesla_climate_concierge.service import ClimateConciergeService
from tesla_climate_concierge.simulator import FakeTeslaClient, demo_vehicles
from datetime import datetime


def _start_server():
    settings = Settings(vehicles=[VehicleConfig("Model Y", "VINY")],
                        ai_mode="never")
    fake = FakeTeslaClient(demo_vehicles())
    service = ClimateConciergeService(settings, client_factory=lambda: fake,
                                      now_fn=lambda: datetime(2026, 10, 29, 12, 0))
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(service))
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    return httpd, f"http://127.0.0.1:{httpd.server_address[1]}"


def _call(base, method, path, payload=None):
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(base + path, data=data, method=method,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=10) as resp:
        return resp.status, json.loads(resp.read())


def test_http_endpoints():
    httpd, base = _start_server()
    try:
        status, models = _call(base, "GET", "/v1/models")
        assert status == 200 and models["object"] == "list"
        status, chat = _call(base, "POST", "/v1/chat/completions",
                             {"model": "tesla-climate-concierge",
                              "messages": [{"role": "user",
                                            "content": "early flight!! leave 5ish to LAX"}]})
        assert status == 200
        assert chat["object"] == "chat.completion"
        assert "5:00 AM" in chat["choices"][0]["message"]["content"]
        status, emb = _call(base, "POST", "/v1/embeddings",
                            {"input": "early flight"})
        assert status == 200 and len(emb["data"][0]["embedding"]) == 384
        status, health = _call(base, "GET", "/health")
        assert status == 200 and health["status"] == "ok"
    finally:
        httpd.shutdown()
        httpd.server_close()
