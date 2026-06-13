from urllib.parse import quote_plus

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Octopus Energy credentials
    octopus_email: str = ""
    octopus_password: str = ""
    # API key for programmatic access (preferred — no captcha required)
    # Generate at: octopus.energy → Account → Personal details → API access
    octopus_api_key: str = ""
    offer_url: str = (
        "https://octopus.energy/dashboard/new/accounts/A-C6CD43B6/octoplus/partner/offer-group/925"
    )

    # PostgreSQL
    postgres_host: str = "db"
    postgres_port: int = 5432
    postgres_db: str = "octoscrape"
    postgres_user: str = "octoscrape"
    postgres_password: str

    # App
    secret_key: str = "changeme"

    @property
    def database_url(self) -> str:
        # URL-encode credentials to handle special characters (@, %, !, etc.)
        user = quote_plus(self.postgres_user)
        password = quote_plus(self.postgres_password)
        return (
            f"postgresql+asyncpg://{user}:{password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )


settings = Settings()  # type: ignore[call-arg]
