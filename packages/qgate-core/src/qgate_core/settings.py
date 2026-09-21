"""Environment-driven settings shared by every service. Defaults target `make up-infra`."""

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    kafka_bootstrap: str = "localhost:19092"
    schema_registry_url: str = "http://localhost:8081"
    schemas_dir: Path = Field(default=Path("schemas"), validation_alias="QGATE_SCHEMAS_DIR")
    database_url: str = ""  # each service receives the URL for its own role
