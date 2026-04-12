from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Database
    database_url: str = "postgresql+asyncpg://app:app@localhost:5434/app"

    # SMTP
    smtp_host: str = "mailpit"
    smtp_port: int = 1025
    smtp_sender: str = "noreply@example.com"

    # Service metadata
    service_name: str = "notification-service"
    service_version: str = "0.1.0"
    log_level: str = "INFO"


settings = Settings()
