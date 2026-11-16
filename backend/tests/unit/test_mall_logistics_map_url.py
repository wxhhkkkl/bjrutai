from types import SimpleNamespace

from src.services import mall_logistics_service as service

TRAIL_URL = "https://api.kuaidi100.com/tools/map/V2/token_117.2272,31.8206_6"


def _settings(monkeypatch, *, base="", environment="test"):
    monkeypatch.setattr(
        service,
        "get_settings",
        lambda: SimpleNamespace(
            kuaidi100_map_public_base=base, app_environment=environment
        ),
    )


def test_public_map_url_rewrites_configured_wrapper_base(monkeypatch):
    _settings(monkeypatch, base="https://kuaidi.example.com/", environment="production")
    assert service._public_map_url(TRAIL_URL) == (
        "https://kuaidi.example.com/mall-map.html?u="
        "https%3A%2F%2Fapi.kuaidi100.com%2Ftools%2Fmap%2FV2%2Ftoken_117.2272%2C31.8206_6"
    )


def test_public_map_url_hides_direct_trail_in_production(monkeypatch):
    _settings(monkeypatch, environment="production")
    assert service._public_map_url(TRAIL_URL) is None


def test_public_map_url_allows_direct_trail_outside_production(monkeypatch):
    _settings(monkeypatch, environment="development")
    assert service._public_map_url(TRAIL_URL) == TRAIL_URL


def test_public_map_url_rejects_non_kuaidi_hosts(monkeypatch):
    _settings(monkeypatch, base="https://kuaidi.example.com", environment="production")
    assert service._public_map_url("https://example.com/tools/map/V2/token") is None
