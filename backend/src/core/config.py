from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    # Database
    database_url: str = "mysql+aiomysql://user:password@host:3306/bjrutai?charset=utf8mb4"

    # WeChat
    wechat_app_id: str = ""
    wechat_app_secret: str = ""

    # JWT
    jwt_secret_key: str = "dev-secret-change-in-production"
    access_token_expire_minutes: int = 120
    refresh_token_expire_days: int = 30

    # Rutai API
    rutai_api_base_url: str = "https://api.rutai.example.com"
    rutai_api_key: str = ""
    rutai_api_secret: str = ""

    # COS
    cos_secret_id: str = ""
    cos_secret_key: str = ""
    cos_bucket: str = ""
    cos_region: str = "ap-beijing"

    # Rate limiting
    rate_limit_enabled: bool = True
    rate_limit_requests_per_minute: int = 10

    # Admin
    admin_default_username: str = "admin"
    admin_default_password: str = "change-me"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


@lru_cache()
def get_settings() -> Settings:
    return Settings()
