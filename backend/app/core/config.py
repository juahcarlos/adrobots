from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    keitaro_api_url: str
    keitaro_api_token: str
    database_url: str
    group_id: str = "10332"
    log_level: str = "INFO"
    keitaro_timeout: float = 30.0
    cors_origins: list[str] = ["http://localhost:5173"]
