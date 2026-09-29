"""Parameterised asset queries (WP5.5): BigQuery GIS with a local GeoPandas/NumPy fallback of identical signature.

Gemini never writes SQL. The agent can only call these three fixed, parameterised queries:
``assets_within``, ``assets_in_district`` and ``top_priority``.
"""

from __future__ import annotations

from typing import Any, Protocol

import numpy as np
import pandas as pd

from services.config import get_settings

CLASS_RANK = {"LOW": 0, "MODERATE": 1, "HIGH": 2, "CRITICAL": 3}
RESULT_COLUMNS = ["name", "asset_type", "osm_element", "osm_id", "district", "lat", "lon", "class_v2", "combined_v2",
                  "triage_tier", "dominant_hazard", "facility_quality"]
MAX_ROWS = 50


class AssetQueries(Protocol):
    backend: str

    def assets_within(self, lat: float, lon: float, radius_km: float, types: list[str] | None = None, min_class: str = "LOW") -> list[dict[str, Any]]: ...
    def assets_in_district(self, district: str, types: list[str] | None = None, min_class: str = "LOW") -> list[dict[str, Any]]: ...
    def top_priority(self, department: str, n: int = 15) -> list[dict[str, Any]]: ...


def _rank(min_class: str) -> int:
    if min_class not in CLASS_RANK:
        raise ValueError(f"min_class must be one of {list(CLASS_RANK)}")
    return CLASS_RANK[min_class]


def build_assets_table(region_id: str | None = None) -> pd.DataFrame:
    """The table loaded into BigQuery and used by the local fallback: v2 scores, district and class rank per asset."""
    from services.assets import load_all_assets
    from services.departments import score_all_assets
    from services.exposure import assign_districts

    scored = score_all_assets(region_id=region_id)
    base = load_all_assets(region_id)[["osm_element", "osm_id", "distance_to_track_km"]]
    table = scored.merge(base, on=["osm_element", "osm_id"], how="left")
    table["district"] = assign_districts(table, region_id)["district"].to_numpy()
    table["class_rank"] = table["class_v2"].map(CLASS_RANK).astype(int)
    if "facility_quality" not in table:
        table["facility_quality"] = "not_applicable"
    return table


def _clean(frame: pd.DataFrame) -> list[dict[str, Any]]:
    out = frame[[c for c in RESULT_COLUMNS + ["distance_km"] if c in frame.columns]].head(MAX_ROWS)
    out = out.round({"lat": 5, "lon": 5, "combined_v2": 3, "distance_km": 2})
    return out.astype(object).where(out.notna(), None).to_dict(orient="records")


class LocalAssetQueries:
    backend = "local"

    def __init__(self, table: pd.DataFrame | None = None) -> None:
        self._table = table

    @property
    def table(self) -> pd.DataFrame:
        if self._table is None:
            self._table = build_assets_table()
        return self._table

    def assets_within(self, lat, lon, radius_km, types=None, min_class="LOW"):
        from services.hazards.coast import haversine_matrix_km

        t = self.table
        distance = haversine_matrix_km(np.array([lat]), np.array([lon]), t["lat"].to_numpy(float), t["lon"].to_numpy(float))[0]
        mask = (distance <= radius_km) & (t["class_rank"] >= _rank(min_class))
        if types:
            mask &= t["asset_type"].isin(types).to_numpy()
        return _clean(t.assign(distance_km=distance)[mask].sort_values("distance_km"))

    def assets_in_district(self, district, types=None, min_class="LOW"):
        t = self.table
        mask = (t["district"].str.lower() == district.lower()) & (t["class_rank"] >= _rank(min_class))
        if types:
            mask &= t["asset_type"].isin(types)
        return _clean(t[mask].sort_values("combined_v2", ascending=False))

    def top_priority(self, department, n=15):
        from services.departments import department_mask, get_department

        t = self.table
        ranked = t[department_mask(get_department(department), t)].sort_values("combined_v2", ascending=False)
        return _clean(ranked.head(min(n, MAX_ROWS)))


class BigQueryAssetQueries:
    backend = "bigquery"

    def __init__(self, project: str | None = None, dataset: str | None = None) -> None:
        from google.cloud import bigquery

        settings = get_settings()
        self.bq = bigquery
        self.client = bigquery.Client(project=project or settings.cloud_project)
        self.table = f"`{self.client.project}.{dataset or settings.bq_dataset}.assets`"

    def _run(self, sql: str, params: list[Any]) -> list[dict[str, Any]]:
        job = self.client.query(sql, job_config=self.bq.QueryJobConfig(query_parameters=params))
        return _clean(job.result().to_dataframe())

    def assets_within(self, lat, lon, radius_km, types=None, min_class="LOW"):
        sql = f"""SELECT name, asset_type, osm_element, osm_id, district, lat, lon, class_v2, combined_v2, triage_tier,
                   dominant_hazard, facility_quality, ST_DISTANCE(geog, ST_GEOGPOINT(@lon, @lat)) / 1000 AS distance_km
                  FROM {self.table}
                  WHERE ST_DWITHIN(geog, ST_GEOGPOINT(@lon, @lat), @radius_m) AND class_rank >= @rank
                    AND (ARRAY_LENGTH(@types) = 0 OR asset_type IN UNNEST(@types))
                  ORDER BY distance_km LIMIT {MAX_ROWS}"""
        p = self.bq
        return self._run(sql, [p.ScalarQueryParameter("lat", "FLOAT64", lat), p.ScalarQueryParameter("lon", "FLOAT64", lon),
                               p.ScalarQueryParameter("radius_m", "FLOAT64", radius_km * 1000), p.ScalarQueryParameter("rank", "INT64", _rank(min_class)),
                               p.ArrayQueryParameter("types", "STRING", types or [])])

    def assets_in_district(self, district, types=None, min_class="LOW"):
        sql = f"""SELECT name, asset_type, osm_element, osm_id, district, lat, lon, class_v2, combined_v2, triage_tier,
                   dominant_hazard, facility_quality
                  FROM {self.table}
                  WHERE LOWER(district) = LOWER(@district) AND class_rank >= @rank
                    AND (ARRAY_LENGTH(@types) = 0 OR asset_type IN UNNEST(@types))
                  ORDER BY combined_v2 DESC LIMIT {MAX_ROWS}"""
        p = self.bq
        return self._run(sql, [p.ScalarQueryParameter("district", "STRING", district), p.ScalarQueryParameter("rank", "INT64", _rank(min_class)),
                               p.ArrayQueryParameter("types", "STRING", types or [])])

    def top_priority(self, department, n=15):
        from services.departments import get_department

        dept = get_department(department)
        sql = f"""SELECT name, asset_type, osm_element, osm_id, district, lat, lon, class_v2, combined_v2, triage_tier,
                   dominant_hazard, facility_quality
                  FROM {self.table}
                  WHERE asset_type IN UNNEST(@types)
                    AND (asset_type != 'hospital' OR ARRAY_LENGTH(@quality) = 0 OR facility_quality IN UNNEST(@quality))
                  ORDER BY IF(asset_type = 'hospital' AND facility_quality != 'hospital', 1, 0), combined_v2 DESC LIMIT @n"""
        p = self.bq
        return self._run(sql, [p.ArrayQueryParameter("types", "STRING", list(dept.asset_types)),
                               p.ArrayQueryParameter("quality", "STRING", list(dept.facility_quality)),
                               p.ScalarQueryParameter("n", "INT64", min(n, MAX_ROWS))])


def get_asset_queries() -> AssetQueries:
    """BigQuery when ``SURGESIGHT_ASSET_BACKEND=bigquery`` and the table exists, otherwise the local fallback."""
    import os

    if os.getenv("SURGESIGHT_ASSET_BACKEND", "local") == "bigquery":
        try:
            queries = BigQueryAssetQueries()
            queries.client.get_table(queries.table.strip("`"))
            return queries
        except Exception:
            pass
    return LocalAssetQueries()
