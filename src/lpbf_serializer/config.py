"""Application configuration.

All settings are explicit. There are no runtime-synthesised defaults for
paths that point outside the user's home directory. If the environment or
TOML file specifies a value, we use it verbatim; otherwise we pick a path
under ``%LOCALAPPDATA%`` / ``~/.local/share`` and create it on first use.
"""

from __future__ import annotations

import os
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


def _default_data_dir() -> Path:
    if os.name == "nt":
        base = os.environ.get("LOCALAPPDATA")
        if base is None:
            raise RuntimeError(
                "LOCALAPPDATA is not set; refusing to guess a data directory."
            )
        return Path(base) / "LPBFSerializer"
    xdg = os.environ.get("XDG_DATA_HOME")
    if xdg is not None:
        return Path(xdg) / "lpbf-serializer"
    return Path.home() / ".local" / "share" / "lpbf-serializer"


class Settings(BaseSettings):
    """Runtime settings.

    Load order (later wins): defaults -> ``lpbf-serializer.toml`` in CWD ->
    environment variables prefixed ``LPBF_``.
    """

    model_config = SettingsConfigDict(
        env_prefix="LPBF_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="forbid",
    )

    data_dir: Path = Field(default_factory=_default_data_dir)
    database_url: str | None = None

    quantam_exe: Path = Path(
        r"C:\Program Files\Renishaw\Renishaw QuantAM 6.1.0.1\Renishaw QuantAM.exe"
    )
    quantam_expected_version: str = "6.1.0.1"

    build_code_prefix: str = "B#"
    build_code_digits: int = 4

    plate_width_mm: float = 250.0
    plate_depth_mm: float = 250.0

    export_dir_name: str = "exported-mtt"
    report_dir_name: str = "reports"

    @property
    def db_path(self) -> Path:
        return self.data_dir / "lpbf.sqlite3"

    @property
    def effective_database_url(self) -> str:
        if self.database_url is not None:
            return self.database_url
        return f"sqlite:///{self.db_path.as_posix()}"

    @property
    def export_dir(self) -> Path:
        return self.data_dir / self.export_dir_name

    @property
    def report_dir(self) -> Path:
        return self.data_dir / self.report_dir_name

    def ensure_dirs(self) -> None:
        for d in (self.data_dir, self.export_dir, self.report_dir):
            d.mkdir(parents=True, exist_ok=True)


def load_settings() -> Settings:
    return Settings()
