import pytest
from pydantic import ValidationError

from src.core.config import Settings


def test_runtime_defaults_closed_and_production_cannot_create_schema():
    settings = Settings(_env_file=None)
    assert not settings.schema_auto_create_enabled
    assert not settings.mall_gateway_outbound_enabled
    assert not settings.mall_storage_outbound_enabled
    with pytest.raises(ValidationError):
        Settings(_env_file=None, app_environment="production", schema_auto_create_enabled=True)
    with pytest.raises(ValidationError):
        Settings(_env_file=None, mall_gateway_mode="test", mall_gateway_outbound_enabled=True)


def test_sensitive_config_values_are_not_in_repr():
    settings = Settings(
        _env_file=None,
        cos_secret_id="private-cos-id",
        cos_secret_key="private-cos-key",
        jwt_secret_key="private-jwt",
    )
    assert "private-cos-id" not in repr(settings)
    assert "private-cos-key" not in repr(settings)
    assert "private-jwt" not in repr(settings)
