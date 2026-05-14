from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

APP_DIR = Path(__file__).resolve().parent
SERVER_DIR = APP_DIR.parent
REPO_ROOT = SERVER_DIR.parent
DATA_DIR = REPO_ROOT / "data"


class RanobarrBaseSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file="../.env",
        env_file_encoding="utf-8",
        env_prefix="RANOBARR__",
        env_nested_delimiter="__",
        extra="ignore",
    )


class AppConfig(RanobarrBaseSettings):
    project_name: str = "Ranobarr"
    data_dir: Path = DATA_DIR
    database_name: str = "ranobarr.db"
    artifacts_dir_name: str = "artifacts"
    cache_dir_name: str = "cache"
    temp_dir_name: str = "tmp"
    cors_allow_origins: list[str] = Field(default_factory=lambda: ["http://127.0.0.1:5173"])
    cors_allow_origin_regex: str | None = None
    cors_allow_credentials: bool = True
    cors_allow_methods: list[str] = Field(default_factory=lambda: ["GET", "POST", "PUT", "PATCH", "DELETE"])
    cors_allow_headers: list[str] = Field(default_factory=lambda: ["*"])

    @property
    def database_url(self) -> str:
        return f"sqlite+aiosqlite:///{self.data_dir / self.database_name}"

    @property
    def artifacts_dir(self) -> Path:
        return self.data_dir / self.artifacts_dir_name

    @property
    def cache_dir(self) -> Path:
        return self.data_dir / self.cache_dir_name

    @property
    def temp_dir(self) -> Path:
        return self.data_dir / self.temp_dir_name


class ServerConfig(RanobarrBaseSettings):
    host: str = "127.0.0.1"
    port: int = 3030


class SchedulerConfig(RanobarrBaseSettings):
    scan_interval_seconds: int = 900


class Settings(RanobarrBaseSettings):
    app: AppConfig = Field(default_factory=AppConfig)
    server: ServerConfig = Field(default_factory=ServerConfig)
    scheduler: SchedulerConfig = Field(default_factory=SchedulerConfig)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
