from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg://majorauto:majorauto@localhost:5432/majorauto"
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-sonnet-4-5-20250929"

    # city -> path/URL of its feed XML. Local file paths for now; swap a
    # value for an https:// URL once real feed endpoints are known.
    # data/feeds/ is gitignored - the real Major feed lives there, not in
    # the repo (it's large, goes stale, and this is meant to be fetched by
    # the periodic ETL job eventually, not committed).
    feed_sources: dict[str, str] = {
        "Москва": "data/feeds/msk.xml",
    }


settings = Settings()
