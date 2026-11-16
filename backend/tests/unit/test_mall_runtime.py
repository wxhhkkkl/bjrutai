import pytest
from pydantic import ValidationError

from src.core.config import Settings


def test_runtime_defaults_closed_and_production_cannot_create_schema():
    settings = Settings(_env_file=None)
    assert not settings.schema_auto_create_enabled
    assert not settings.mall_gateway_outbound_enabled
    assert not settings.mall_storage_outbound_enabled
    assert settings.mall_kuaidi100_mode == "fake"
    assert not settings.mall_kuaidi100_outbound_enabled
    assert not settings.kuaidi100_customer and not settings.kuaidi100_key
    with pytest.raises(ValidationError):
        Settings(_env_file=None, app_environment="production", schema_auto_create_enabled=True)
    with pytest.raises(ValidationError):
        Settings(_env_file=None, mall_gateway_mode="test", mall_gateway_outbound_enabled=True)
    with pytest.raises(ValidationError):
        Settings(
            _env_file=None,
            app_environment="test",
            mall_kuaidi100_outbound_enabled=True,
        )


def test_logistics_credentials_are_hidden_from_runtime_repr():
    settings = Settings(
        _env_file=None,
        kuaidi100_customer="private-kuaidi-customer",
        kuaidi100_key="private-kuaidi-key",
    )
    assert "private-kuaidi-customer" not in repr(settings)
    assert "private-kuaidi-key" not in repr(settings)


def test_sensitive_config_values_are_not_in_repr():
    settings = Settings(
        _env_file=None,
        cos_secret_id="private-cos-id",
        cos_secret_key="private-cos-key",
        jwt_secret_key="private-jwt",
        mall_wechat_api_v2_key="0123456789abcdef0123456789abcdef",
        mall_wechat_refund_client_key_path="private-refund-key-path",
        mall_prepay_keys={"k1": "private-prepay-key"},
    )
    assert "private-cos-id" not in repr(settings)
    assert "private-cos-key" not in repr(settings)
    assert "private-jwt" not in repr(settings)
    assert "0123456789abcdef0123456789abcdef" not in repr(settings)
    assert "private-refund-key-path" not in repr(settings)
    assert "private-prepay-key" not in repr(settings)


def test_payment_runtime_is_closed_and_rejects_changed_original_subject(monkeypatch):
    from types import SimpleNamespace

    from src.core.config import get_settings
    from src.integrations.wechat_pay_types import PaymentGatewayError
    from src.services.mall_payment_runtime import payment_runtime

    original = SimpleNamespace(appid_snapshot="old-app", mchid_snapshot="old-merchant")
    with pytest.raises(PaymentGatewayError):
        payment_runtime(original)
    monkeypatch.setattr(get_settings(), "mall_gateway_mode", "live")
    monkeypatch.setattr(get_settings(), "mall_gateway_outbound_enabled", True)
    with pytest.raises(PaymentGatewayError, match="payment_configuration_changed"):
        payment_runtime(original)


def test_payment_worker_handler_registration_is_closed_by_default(monkeypatch):
    from src.core.config import get_settings
    from src.services.mall_payment_runtime import payment_handlers

    monkeypatch.setattr(get_settings(), "mall_gateway_mode", "test")
    monkeypatch.setattr(get_settings(), "mall_gateway_outbound_enabled", False)
    assert payment_handlers(None) == {}


def test_data_release_gate_fails_closed_and_production_requires_governance_references():
    # Feature flag alone never enables anything.
    dev = Settings(_env_file=None, mall_data_release_enabled=True)
    assert dev.mall_data_release_retention_policy_ref == ""
    assert dev.mall_data_release_notice_approved_version == ""
    # Production cannot enable raw release without both approved references.
    with pytest.raises(ValidationError):
        Settings(
            _env_file=None,
            app_environment="production",
            mall_data_release_enabled=True,
        )
    with pytest.raises(ValidationError):
        Settings(
            _env_file=None,
            app_environment="production",
            mall_data_release_enabled=True,
            mall_data_release_retention_policy_ref="approved-retention-v1",
        )
    with pytest.raises(ValidationError):
        Settings(
            _env_file=None,
            app_environment="production",
            mall_data_release_enabled=True,
            mall_data_release_notice_approved_version="notice-v1",
        )
    configured = Settings(
        _env_file=None,
        app_environment="production",
        mall_data_release_enabled=True,
        mall_data_release_retention_policy_ref="approved-retention-v1",
        mall_data_release_notice_approved_version="notice-v1",
    )
    assert configured.mall_data_release_enabled


def test_data_release_runtime_ready_requires_flag_and_both_references(monkeypatch):
    from src.core.config import get_settings
    from src.services.mall_data_release_service import raw_data_release_runtime_ready

    settings = get_settings()
    monkeypatch.setattr(settings, "mall_data_release_enabled", True, raising=False)
    monkeypatch.setattr(
        settings, "mall_data_release_retention_policy_ref", "approved-retention-v1", raising=False
    )
    monkeypatch.setattr(
        settings, "mall_data_release_notice_approved_version", "notice-v1", raising=False
    )
    assert raw_data_release_runtime_ready(settings)

    monkeypatch.setattr(settings, "mall_data_release_enabled", False, raising=False)
    assert not raw_data_release_runtime_ready(settings)
    monkeypatch.setattr(settings, "mall_data_release_enabled", True, raising=False)
    monkeypatch.setattr(settings, "mall_data_release_retention_policy_ref", "", raising=False)
    assert not raw_data_release_runtime_ready(settings)
    monkeypatch.setattr(
        settings, "mall_data_release_retention_policy_ref", "approved-retention-v1", raising=False
    )
    monkeypatch.setattr(settings, "mall_data_release_notice_approved_version", "", raising=False)
    assert not raw_data_release_runtime_ready(settings)
