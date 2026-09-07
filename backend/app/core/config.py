import os
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
RESOURCES = ROOT / "backend/app/resources"


@dataclass(frozen=True)
class Settings:
    data_dir: Path
    database_url: str
    max_upload_bytes: int = 80 * 1024 * 1024
    workers: int = 2

    @classmethod
    def from_env(cls):
        data = Path(os.getenv("KANZLER_DATA_DIR", str(ROOT / "data"))).resolve()
        return cls(
            data, os.getenv("KANZLER_DATABASE_URL", f"sqlite:///{(data / 'database/platform.db').as_posix()}")
        )
