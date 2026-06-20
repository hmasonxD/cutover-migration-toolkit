"""Central configuration. Connection strings come from the environment so the
same code runs against a local dev cluster, a CI service, or a staging mirror of
a municipality's data without edits."""
from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="CUTOVER_", extra="ignore")

    # The municipality's outgoing legacy system (read-only in real life).
    legacy_host: str = "localhost"
    legacy_port: int = 5432
    legacy_db: str = "legacy_muni"
    legacy_user: str = "postgres"
    legacy_password: str = ""

    # The Catalis cloud target.
    cloud_host: str = "localhost"
    cloud_port: int = 5432
    cloud_db: str = "catalis_cloud"
    cloud_user: str = "postgres"
    cloud_password: str = ""

    # Base URL of the running cloud API used for API-based validation.
    api_base_url: str = "http://127.0.0.1:8000"

    @property
    def legacy_dsn(self) -> str:
        return (
            f"host={self.legacy_host} port={self.legacy_port} dbname={self.legacy_db} "
            f"user={self.legacy_user} password={self.legacy_password}"
        )

    @property
    def cloud_dsn(self) -> str:
        return (
            f"host={self.cloud_host} port={self.cloud_port} dbname={self.cloud_db} "
            f"user={self.cloud_user} password={self.cloud_password}"
        )


settings = Settings()