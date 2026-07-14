from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Central app configuration. Values are loaded from environment
    variables / a .env file (see .env.example). Keeping this in one
    place means swapping infra (SQLite -> Postgres, memory cache ->
    Redis) later only touches this file and the relevant impl module.
    """

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: str = "development"
    api_v1_prefix: str = "/api/v1"

    cors_origins: str = "http://localhost:4000"

    database_url: str = "sqlite:///./stock_insights.db"

    cache_ttl_seconds: int = 15 * 60

    alpha_vantage_api_key: str | None = None

    # "AI Pick of the Day" (see services/recommendation_service.py). Only
    # needed by the daily batch job (scripts/generate_recommendation.py) --
    # the API endpoint itself is a pure DB read of whatever that job last
    # wrote, so this key never needs to live on Render, only wherever the
    # daily refresh runs (GitHub Actions secret, per DEPLOYMENT.md).
    anthropic_api_key: str | None = None
    anthropic_model: str = "claude-sonnet-5"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


settings = Settings()
