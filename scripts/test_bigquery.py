"""BigQuery GIS asset queries must match the local fallback (WP5.5)."""

from __future__ import annotations

import os
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import services.agent  # noqa: F401
from services.agent.tools import execute_tool
from services.store.bigquery_store import LocalAssetQueries


def key(rows):
    return [(r["osm_element"], int(r["osm_id"])) for r in rows]


def main() -> None:
    local = LocalAssetQueries()
    near = local.assets_within(13.0827, 80.2707, 5, ["hospital"], "HIGH")
    assert near and all(r["asset_type"] == "hospital" and r["distance_km"] <= 5 for r in near)
    assert [r["distance_km"] for r in near] == sorted(r["distance_km"] for r in near)
    guntur = local.assets_in_district("guntur", ["substation"], "HIGH")
    assert guntur and all(r["district"] == "Guntur" for r in guntur)
    top = local.top_priority("Fisheries Department", 5)
    assert top and all(r["asset_type"] == "fishing_harbour" for r in top)
    try:
        local.assets_within(13, 80, 5, None, "DROP TABLE")
        raise AssertionError("bad min_class must be rejected")
    except ValueError:
        pass
    result, _ = execute_tool("assets_within", {"lat": 13.0827, "lon": 80.2707, "radius_km": 5, "types": ["hospital"]})
    assert result.ok and result.data["count"] > 0 and result.data["backend"] == "local"
    print("local queries ok")
    if os.getenv("SURGESIGHT_OFFLINE") == "1":
        print("SKIPPED BigQuery comparison (SURGESIGHT_OFFLINE=1)")
        return
    from services.store.bigquery_store import BigQueryAssetQueries

    bq = BigQueryAssetQueries()
    b_near = bq.assets_within(13.0827, 80.2707, 5, ["hospital"], "HIGH")
    assert set(key(b_near)) == set(key(near)), (len(b_near), len(near))
    assert set(key(bq.assets_in_district("guntur", ["substation"], "HIGH"))) == set(key(guntur))
    assert key(bq.top_priority("Fisheries Department", 5)) == key(top) or set(key(bq.top_priority("Fisheries Department", 5))) == set(key(top))
    health = bq.top_priority("Health Department", 5)
    assert health and all(r["asset_type"] == "hospital" and r["facility_quality"] == "hospital" for r in health)
    print("bigquery matches local")
    print("SURGESIGHT_BIGQUERY_OK")


if __name__ == "__main__":
    main()
