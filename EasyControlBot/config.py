from zoneinfo import ZoneInfo

from pydantic_settings import BaseSettings, SettingsConfigDict

# Единый часовой пояс для всего бота
TZ = ZoneInfo("Europe/Moscow")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    bot_token: str
    admin_id: int
    database_url: str


config = Settings()  # pyright: ignore[reportCallIssue]