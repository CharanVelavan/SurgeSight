"""Land-mask + Earth Engine helper test (K3)."""

from __future__ import annotations

import json
import os
from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

SUMMARY = PROJECT_ROOT / "data/processed/michaung_terrain_summary.json"


def main() -> None:
    summary = json.loads(SUMMARY.read_text(encoding="utf-8"))
    assert summary.get("land_mask", {}).get("country") == "India", "summary not land-masked"
    assert "project" not in summary, "project id must not be written to the summary"
    stats = summary["summary"]
    assert stats["very_low_percentage"] < 20, stats["very_low_percentage"]
    assert stats["mean_elevation_m"] > 100, stats["mean_elevation_m"]
    print("summary checks passed")

    if os.getenv("SURGESIGHT_OFFLINE") == "1":
        print("SKIPPED Earth Engine helper checks (SURGESIGHT_OFFLINE=1)")
        return

    import ee
    from services.earth_engine import init_ee, land_mask, sample_points, thumbnail_png

    init_ee()
    elevation = ee.Image("USGS/SRTMGL1_003").select("elevation")
    image = elevation.addBands(land_mask("India").rename("land"))
    chennai, bay = (13.0827, 80.2707), (13.0, 82.5)  # city, open Bay of Bengal
    city, sea = sample_points(image, [chennai, bay], scale=30)
    assert city["land"] == 1, city
    assert sea["land"] is None, sea
    print("sample_points ok:", city)

    png = thumbnail_png(
        elevation.updateMask(land_mask("India")),
        [79.0, 11.5, 82.0, 15.0],
        {"min": 0, "max": 500, "palette": ["0b3d91", "2e8b57", "f5deb3", "8b4513"]},
        dimensions=256,
    )
    assert png[:8] == b"\x89PNG\r\n\x1a\n", "not a PNG"
    print(f"thumbnail ok: {len(png)} bytes")
    print("SURGESIGHT_TERRAIN_LANDMASK_OK")


if __name__ == "__main__":
    main()
