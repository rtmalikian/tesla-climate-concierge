"""Configuration for Tesla Climate Concierge. All settings come from the
environment (see .env.example). Copy .env.example to .env — .env is
git-ignored so secrets never leave your machine."""
from __future__ import annotations

import os
from dataclasses import dataclass, field


class ConfigError(Exception):
    pass


@dataclass
class VehicleConfig:
    name: str
    vin: str = ""   # may be blank: nickname-only cars get a VIN at pairing time


@dataclass
class Settings:
    client_id: str = ""
    client_secret: str = ""
    region: str = "na"
    redirect_uri: str = "http://localhost:8080/callback"
    token_file: str = "~/.tcc/tokens.json"
    vehicles: list[VehicleConfig] = field(default_factory=list)
    # The OpenAI-compatible server this app exposes.
    server_host: str = "127.0.0.1"
    server_port: int = 8643
    server_api_key: str = ""          # optional bearer token for /v1/*
    model_id: str = "tesla-climate-concierge"
    # Pluggable LLM backend (any OpenAI-compatible API; default: local Ollama).
    ai_base_url: str = "http://localhost:11434/v1"
    ai_api_key: str = ""
    ai_model: str = "llama3.1"
    ai_mode: str = "auto"             # auto | always | never
    ai_timeout_seconds: float = 20.0
    embedding_dim: int = 384
    dry_run: bool = False
    # Climate-concierge defaults.
    default_temp_f: int = 70
    cop_rearm: bool = True


def _parse_vehicles(raw: str) -> list[VehicleConfig]:
    """Format: name=VIN,name2=VIN2, or bare nicknames (VIN filled in later)."""
    vehicles = []
    for idx, item in enumerate(raw.split(",")):
        item = item.strip()
        if not item:
            continue
        name = None
        if "=" in item:
            name, item = item.split("=", 1)
            name = name.strip()
        vin = item.strip()
        vehicles.append(VehicleConfig(name=name or f"car-{idx + 1}", vin=vin))
    if not vehicles:
        raise ConfigError("TCC_VEHICLES is empty — add at least one car nickname")
    return vehicles


def _int(env: dict, key: str, default: int) -> int:
    raw = env.get(key)
    if raw is None or not str(raw).strip():
        return default
    try:
        return int(raw)
    except (ValueError, TypeError) as exc:
        raise ConfigError(f"{key} must be an integer, got {raw!r}") from exc


def _float(env: dict, key: str, default: float) -> float:
    raw = env.get(key)
    if raw is None or not str(raw).strip():
        return default
    try:
        return float(raw)
    except (ValueError, TypeError) as exc:
        raise ConfigError(f"{key} must be a number, got {raw!r}") from exc


def _bool(env: dict, key: str, default: bool = False) -> bool:
    raw = env.get(key)
    if raw is None:
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


def load_settings(env: dict | None = None) -> Settings:
    env = os.environ if env is None else env
    s = Settings()
    s.client_id = env.get("TESLA_CLIENT_ID", "")
    s.client_secret = env.get("TESLA_CLIENT_SECRET", "")
    s.region = env.get("TESLA_REGION", "na").strip().lower()
    if s.region not in ("na", "eu", "cn"):
        raise ConfigError(f"TESLA_REGION must be na|eu|cn, got {s.region!r}")
    s.redirect_uri = env.get("TESLA_REDIRECT_URI", s.redirect_uri)
    s.token_file = env.get("TCC_TOKEN_FILE", s.token_file)
    raw_vehicles = env.get("TCC_VEHICLES", "")
    if raw_vehicles.strip():
        s.vehicles = _parse_vehicles(raw_vehicles)
    s.server_host = env.get("TCC_SERVER_HOST", s.server_host)
    s.server_port = _int(env, "TCC_SERVER_PORT", s.server_port)
    s.server_api_key = env.get("TCC_SERVER_API_KEY", "")
    s.model_id = env.get("TCC_MODEL_ID", s.model_id)
    s.ai_base_url = env.get("TCC_AI_BASE_URL", s.ai_base_url).rstrip("/")
    s.ai_api_key = env.get("TCC_AI_API_KEY", "")
    s.ai_model = env.get("TCC_AI_MODEL", s.ai_model)
    s.ai_mode = env.get("TCC_AI_MODE", s.ai_mode).strip().lower()
    if s.ai_mode not in ("auto", "always", "never"):
        raise ConfigError(f"TCC_AI_MODE must be auto|always|never, got {s.ai_mode!r}")
    s.ai_timeout_seconds = _float(env, "TCC_AI_TIMEOUT_SECONDS", s.ai_timeout_seconds)
    s.embedding_dim = _int(env, "TCC_EMBEDDING_DIM", s.embedding_dim)
    if not (8 <= s.embedding_dim <= 4096):
        raise ConfigError("TCC_EMBEDDING_DIM must be between 8 and 4096")
    s.dry_run = _bool(env, "TCC_DRY_RUN")
    s.default_temp_f = _int(env, "TCC_DEFAULT_TEMP_F", s.default_temp_f)
    if not (50 <= s.default_temp_f <= 85):
        raise ConfigError("TCC_DEFAULT_TEMP_F must be between 50 and 85")
    s.cop_rearm = _bool(env, "TCC_COP_REARM", True)
    return s
