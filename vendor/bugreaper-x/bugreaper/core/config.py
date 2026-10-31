from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="BUGREAPER_", extra="ignore")

    app_name: str = "BugReaper X"
    version: str = "4.0.0"
    debug: bool = False

    api_host: str = "0.0.0.0"
    api_port: int = 8900
    ws_port: int = 8901

    database_url: str = "sqlite+aiosqlite:///./bugreaper.db"
    secret_key: str = "change-this-in-production-kairyx-security"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 1440

    anthropic_api_key: str = ""
    ai_model: str = "claude-sonnet-4-6"

    burp_proxy: str = "http://127.0.0.1:8080"
    burp_api_url: str = "http://127.0.0.1:1337"
    burp_api_key: str = ""

    max_concurrent_scans: int = 5
    default_timeout: int = 30
    rate_limit_per_second: float = 10.0

    cors_origins: list[str] = ["*"]
    allowed_hosts: list[str] = ["*"]


settings = Settings()
