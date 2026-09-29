"""Environment settings and region configuration.

Region files live in ``config/regions/<name>.toml``. Path values stay relative to
the project root (exactly as the previously hard-coded constants were), so
behaviour is unchanged when the working directory is the project root.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache
import os
from pathlib import Path
import tomllib

from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parents[1]
REGIONS_DIR = PROJECT_ROOT / "config" / "regions"
DEFAULT_REGION = "michaung_2023"


@dataclass(frozen=True)
class Settings:
    env: str = "local"                  # local | cloud
    region: str = DEFAULT_REGION
    store: str = "local"                # local | firestore
    offline: bool = False
    dispatch_mode: str = "dry_run"      # dry_run | live
    dispatch_allowlist: tuple[str, ...] = ()
    gemini_model: str = "gemini-3.7-flash"
    use_vertex: bool = False
    cloud_project: str | None = None
    cloud_location: str = "asia-south1"
    ee_project: str | None = None
    bq_dataset: str = "surgesight"
    gcs_bucket: str | None = None


def _flag(name: str, default: str = "0") -> bool:
    return os.getenv(name, default).strip().lower() in {"1", "true", "yes"}


def get_settings() -> Settings:
    """Read settings from the environment (and .env). Secrets are not part of Settings."""
    load_dotenv()
    project = os.getenv("GOOGLE_CLOUD_PROJECT") or None
    allowlist = tuple(
        item.strip() for item in os.getenv("DISPATCH_ALLOWLIST", "").split(",") if item.strip()
    )
    return Settings(
        env=os.getenv("SURGESIGHT_ENV", "local"),
        region=os.getenv("SURGESIGHT_REGION", DEFAULT_REGION),
        store=os.getenv("SURGESIGHT_STORE", "local"),
        offline=_flag("SURGESIGHT_OFFLINE"),
        dispatch_mode=os.getenv("DISPATCH_MODE", "dry_run"),
        dispatch_allowlist=allowlist,
        gemini_model=os.getenv("GEMINI_MODEL", "gemini-3.7-flash"),
        use_vertex=_flag("GOOGLE_GENAI_USE_VERTEXAI", "false"),
        cloud_project=project,
        cloud_location=os.getenv("GOOGLE_CLOUD_LOCATION", "asia-south1"),
        ee_project=os.getenv("EE_PROJECT") or project,
        bq_dataset=os.getenv("BQ_DATASET", "surgesight"),
        gcs_bucket=os.getenv("GCS_BUCKET") or None,
    )


@dataclass(frozen=True)
class Region:
    id: str
    display_name: str
    cyclone_name: str
    ibtracs_sid: str
    country: str
    languages: tuple[str, ...]
    demo_cutoff: str
    bbox: dict[str, float]
    paths: dict[str, Path]
    raw: dict = field(default_factory=dict, repr=False)

    def path(self, key: str) -> Path:
        try:
            return self.paths[key]
        except KeyError as exc:
            raise KeyError(f"Region '{self.id}' has no path '{key}'") from exc


@lru_cache(maxsize=None)
def load_region(name: str | None = None) -> Region:
    """Load ``config/regions/<name>.toml`` (default: SURGESIGHT_REGION or michaung_2023)."""
    name = name or get_settings().region
    file = REGIONS_DIR / f"{name}.toml"
    if not file.exists():
        available = sorted(p.stem for p in REGIONS_DIR.glob("*.toml"))
        raise FileNotFoundError(f"Unknown region '{name}'. Available: {available}")
    data = tomllib.loads(file.read_text(encoding="utf-8"))
    return Region(
        id=data["id"],
        display_name=data["display_name"],
        cyclone_name=data["cyclone_name"],
        ibtracs_sid=data["ibtracs_sid"],
        country=data.get("country", "India"),
        languages=tuple(data.get("languages", ["English"])),
        demo_cutoff=data.get("demo_cutoff", ""),
        bbox=dict(data["bbox"]),
        paths={key: Path(value) for key, value in data.get("paths", {}).items()},
        raw=data,
    )


def list_regions() -> list[str]:
    return sorted(p.stem for p in REGIONS_DIR.glob("*.toml"))
