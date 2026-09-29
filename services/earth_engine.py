"""Earth Engine helpers: initialisation, point sampling, thumbnails, land mask."""

from __future__ import annotations

import os
from typing import Any, Iterable, Sequence

import ee
import requests
from dotenv import load_dotenv


LSIB_ID = "USDOS/LSIB_SIMPLE/2017"
_initialised = False


def init_ee(project: str | None = None) -> str:
    """Initialise Earth Engine once and return the project id used."""
    global _initialised
    load_dotenv()
    project = project or os.getenv("EE_PROJECT") or os.getenv("GOOGLE_CLOUD_PROJECT")
    if not project:
        raise RuntimeError("Set EE_PROJECT or GOOGLE_CLOUD_PROJECT to use Earth Engine")
    if not _initialised:
        ee.Initialize(project=project)
        _initialised = True
    return project


def country_geometry(country_name: str = "India") -> ee.Geometry:
    """Land polygon of a country from LSIB (used as the land mask)."""
    init_ee()
    return (
        ee.FeatureCollection(LSIB_ID)
        .filter(ee.Filter.eq("country_na", country_name))
        .geometry()
    )


def land_mask(country_name: str = "India") -> ee.Image:
    """1 inside the country's land polygon, masked elsewhere."""
    return ee.Image.constant(1).clip(country_geometry(country_name)).selfMask()


def sample_points(
    image: ee.Image,
    points: Iterable[tuple[float, float]] | Sequence[Sequence[float]],
    scale: float,
    *,
    batch_size: int = 500,
) -> list[dict[str, Any]]:
    """Sample image bands at (lat, lon) points.

    Returns one dict per input point, in input order, with the band values
    (None where the image is masked).
    """
    init_ee()
    pts = [(float(lat), float(lon)) for lat, lon in points]
    bands = image.bandNames().getInfo()
    out: list[dict[str, Any]] = []
    for start in range(0, len(pts), batch_size):
        chunk = pts[start : start + batch_size]
        features = [
            ee.Feature(ee.Geometry.Point([lon, lat]), {"_i": start + i})
            for i, (lat, lon) in enumerate(chunk)
        ]
        sampled = image.reduceRegions(
            collection=ee.FeatureCollection(features),
            reducer=ee.Reducer.first(),
            scale=scale,
        ).getInfo()
        by_index = {
            f["properties"]["_i"]: {b: f["properties"].get(b) for b in bands}
            for f in sampled["features"]
        }
        out.extend(by_index.get(start + i, {b: None for b in bands}) for i in range(len(chunk)))
    return out


def thumbnail_png(
    image: ee.Image,
    region: ee.Geometry | Sequence[float],
    vis_params: dict[str, Any] | None = None,
    dimensions: int | str = 768,
) -> bytes:
    """Render an image over a region to PNG bytes.

    region may be an ee.Geometry or [west, south, east, north].
    """
    init_ee()
    if not isinstance(region, ee.Geometry):
        region = ee.Geometry.Rectangle(list(region))
    params = dict(vis_params or {})
    params.update({"region": region, "dimensions": dimensions, "format": "png"})
    url = image.getThumbURL(params)
    response = requests.get(url, timeout=120)
    response.raise_for_status()
    return response.content
