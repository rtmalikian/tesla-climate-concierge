import pytest

from tesla_climate_concierge.config import ConfigError, load_settings


def test_defaults():
    s = load_settings({})
    assert s.default_temp_f == 70
    assert s.cop_rearm is True
    assert s.ai_mode == "auto"
    assert s.server_port == 8643
    assert s.model_id == "tesla-climate-concierge"
    assert s.vehicles == []


def test_tcc_vars_parsed():
    s = load_settings({
        "TCC_VEHICLES": "Model Y=VINY,Model 3=VIN3",
        "TCC_DEFAULT_TEMP_F": "72",
        "TCC_COP_REARM": "0",
        "TCC_AI_MODE": "never",
        "TCC_SERVER_PORT": "9000",
        "TCC_SERVER_API_KEY": "secret",
    })
    assert [v.name for v in s.vehicles] == ["Model Y", "Model 3"]
    assert s.default_temp_f == 72
    assert s.cop_rearm is False
    assert s.ai_mode == "never"
    assert s.server_port == 9000
    assert s.server_api_key == "secret"


def test_nickname_only_vehicle_allowed():
    s = load_settings({"TCC_VEHICLES": "Model Y="})
    assert s.vehicles[0].name == "Model Y"
    assert s.vehicles[0].vin == ""


def test_invalid_ai_mode():
    with pytest.raises(ConfigError):
        load_settings({"TCC_AI_MODE": "sometimes"})


def test_invalid_region():
    with pytest.raises(ConfigError):
        load_settings({"TESLA_REGION": "xx"})


def test_invalid_default_temp():
    with pytest.raises(ConfigError):
        load_settings({"TCC_DEFAULT_TEMP_F": "95"})


def test_bad_port():
    with pytest.raises(ConfigError):
        load_settings({"TCC_SERVER_PORT": "not-a-port"})
