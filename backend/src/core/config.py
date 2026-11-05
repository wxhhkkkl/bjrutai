from functools import lru_cache
from typing import Literal

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    app_environment: Literal["development", "test", "production"] = "development"
    schema_auto_create_enabled: bool = False
    mall_enabled: bool = False
    mall_purchase_enabled: bool = False
    mall_gateway_mode: Literal["test", "live"] = "test"
    mall_gateway_outbound_enabled: bool = False
    # Mall dispatch remains opt-in; domain handlers are independently registered.
    mall_worker_enabled: bool = False
    mall_storage_outbound_enabled: bool = False
    # Database
    database_url: str = Field(
        "mysql+aiomysql://user:password@host:3306/bjrutai?charset=utf8mb4", repr=False
    )

    # WeChat
    wechat_app_id: str = ""
    wechat_app_secret: str = Field("", repr=False)
    public_api_base_url: str = "https://bjrutai.com/api/v1"

    # JWT
    jwt_secret_key: str = Field("dev-secret-change-in-production", repr=False)
    access_token_expire_minutes: int = 120
    refresh_token_expire_days: int = 30

    # Rutai API
    rutai_api_base_url: str = "https://api.rutai.example.com"
    rutai_api_key: str = Field("", repr=False)
    rutai_api_secret: str = Field("", repr=False)
    # Mock the external Rutai API (dev/acceptance without a live 互联网医院对接).
    rutai_mock: bool = False

    # COS
    cos_secret_id: str = Field("", repr=False)
    cos_secret_key: str = Field("", repr=False)
    cos_bucket: str = ""
    cos_region: str = "ap-beijing"

    # Tencent Cloud VOD (browser direct upload; separate, least-privilege credentials)
    vod_secret_id: str = Field("", repr=False)
    vod_secret_key: str = Field("", repr=False)
    vod_sub_app_id: int = 0
    vod_region: str = "ap-beijing"
    vod_procedure: str = ""
    vod_callback_sign_key: str = Field("", repr=False)
    vod_playback_hosts: str = ""  # Exact HTTPS hosts, comma separated
    vod_cleanup_enabled: bool = False  # Enable only after reviewing the deployment

    # Rate limiting
    rate_limit_enabled: bool = True
    rate_limit_requests_per_minute: int = 10

    # Admin
    admin_default_username: str = "admin"
    admin_default_password: str = Field("change-me", repr=False)

    @model_validator(mode="after")
    def validate_mall_runtime(self):
        if self.app_environment == "production" and self.schema_auto_create_enabled:
            raise ValueError("production schema must be managed by Alembic")
        if self.mall_gateway_mode == "test" and self.mall_gateway_outbound_enabled:
            raise ValueError("test gateway cannot perform external money requests")
        return self

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


@lru_cache()
def get_settings() -> Settings:
    return Settings()
