import math
from datetime import datetime

from tesla_climate_concierge.config import Settings, VehicleConfig
from tesla_climate_concierge.service import CAPABILITY_BLURB, ClimateConciergeService
from tesla_climate_concierge.simulator import FakeTeslaClient, demo_vehicles

NOW = datetime(2026, 10, 29, 12, 0)


def make_service(ai_mode="never", llm=None, dry_run=False):
    settings = Settings(vehicles=[VehicleConfig("Model Y", "VINY")],
                        ai_mode=ai_mode, dry_run=dry_run)
    fake = FakeTeslaClient(demo_vehicles())
    service = ClimateConciergeService(settings, client_factory=lambda: fake,
                                      llm_factory=(lambda: llm) if llm is not None else None,
                                      now_fn=lambda: NOW)
    return service, fake


def chat(service, text):
    body = {"model": "tesla-climate-concierge",
            "messages": [{"role": "user", "content": text}]}
    return service.chat_completions(body)


def test_chat_shape_and_event_parse():
    service, _ = make_service()
    resp = chat(service, "early flight!! leave 5ish to LAX")
    assert resp["object"] == "chat.completion"
    msg = resp["choices"][0]["message"]
    assert msg["role"] == "assistant"
    assert "5:00 AM" in msg["content"]
    assert resp["model"] == "tesla-climate-concierge"


def test_word_mapped_temp_survives_service():
    # Regression: "freezing" maps to 74F and must NOT be clobbered back
    # to the 70F default by the service layer.
    service, _ = make_service()
    result = service.parse_and_plan("drive to Big Bear tomorrow 7am, it's freezing")
    assert result["parsed"]["temp_target_f"] == 74
    assert "temp_target_f" not in result["parsed"]["guessed"]
    assert result["plan"]["temp_target_f"] == 74


def test_chat_past_event_is_plain_english():
    service, _ = make_service()
    resp = chat(service, "flight yesterday 5pm")
    content = resp["choices"][0]["message"]["content"]
    assert "already in the past" in content
    assert "Traceback" not in content


def test_models_shape():
    service, _ = make_service()
    models = service.models_list()
    assert models["object"] == "list"
    assert models["data"][0]["id"] == "tesla-climate-concierge"


def test_embeddings_shape_and_determinism():
    service, _ = make_service()
    r1 = service.embeddings({"input": "early flight to lax"})
    r2 = service.embeddings({"input": "early flight to lax"})
    vec = r1["data"][0]["embedding"]
    assert len(vec) == 384
    assert vec == r2["data"][0]["embedding"]
    assert abs(math.sqrt(sum(x * x for x in vec)) - 1.0) < 1e-6


def test_embeddings_batch():
    service, _ = make_service()
    r = service.embeddings({"input": ["one", "two"]})
    assert len(r["data"]) == 2 and r["data"][1]["index"] == 1


class FakeLlm:
    def __init__(self, reply):
        self.reply = reply

    def chat(self, context, user_message):
        return self.reply


def test_llm_fallback_answer():
    llm = FakeLlm("The climate concierge plans from your calendar.")
    service, _ = make_service(ai_mode="auto", llm=llm)
    resp = chat(service, "Tell me a pirate tale about my automobiles")
    assert resp["choices"][0]["message"]["content"].startswith("The climate")


def test_llm_command_block_executes_after_validation():
    llm = FakeLlm('```json\n{"command": "climate_start", "vehicle": "Model Y"}\n```')
    service, fake = make_service(ai_mode="auto", llm=llm)
    resp = chat(service, "Tell me a pirate tale about my automobiles")
    assert fake.command_log == [("auto_conditioning_start", "VINY")]
    assert "climate_start" in resp["choices"][0]["message"]["content"]


def test_llm_disallowed_command_rejected():
    llm = FakeLlm('```json\n{"command": "open_frunk", "vehicle": "Model Y"}\n```')
    service, fake = make_service(ai_mode="auto", llm=llm)
    chat(service, "Tell me a pirate tale about my automobiles")
    assert fake.command_log == []


def test_llm_dry_run_honored():
    llm = FakeLlm('```json\n{"command": "climate_start", "vehicle": "Model Y"}\n```')
    service, fake = make_service(ai_mode="auto", llm=llm, dry_run=True)
    resp = chat(service, "Tell me a pirate tale about my automobiles")
    assert fake.command_log == []
    assert "Dry run" in resp["choices"][0]["message"]["content"]


def test_llm_never_mode_uses_capability_blurb():
    service, _ = make_service(ai_mode="never")
    resp = chat(service, "Tell me a pirate tale about my automobiles")
    assert resp["choices"][0]["message"]["content"] == CAPABILITY_BLURB
