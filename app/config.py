from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg://majorauto:majorauto@localhost:5432/majorauto"
    anthropic_api_key: str = ""

    # city -> path/URL of its feed XML. Local file paths for now; swap a
    # value for an https:// URL once real feed endpoints are known.
    feed_sources: dict[str, str] = {
        "Москва": "fixtures/feed_msk.xml",
    }


settings = Settings()
