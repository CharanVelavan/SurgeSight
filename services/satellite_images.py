"""Map images for the satellite validation: Earth Engine renders, PIL overlays and annotations.

All three images share one extent and one size, so Gemini (and people) can compare them directly.
Labels (graticule and district names) are drawn so a model can name the places it sees.
"""

from __future__ import annotations

import io
import json
from typing import Any

import numpy as np
import pandas as pd
from PIL import Image, ImageDraw, ImageFont
from shapely.geometry import shape

from services.config import load_region

MAX_SIDE = 1024
TIER_COLORS = {1: (214, 40, 40), 2: (245, 130, 32), 3: (250, 204, 21), 4: (74, 160, 96)}
FLOOD_RING = (0, 200, 255)
LAND = (60, 60, 60)
SEA = (14, 30, 46)


def _size(extent: dict[str, float]) -> tuple[int, int]:
    width_deg, height_deg = extent["east"] - extent["west"], extent["north"] - extent["south"]
    scale = MAX_SIDE / max(width_deg, height_deg)
    return int(round(width_deg * scale)), int(round(height_deg * scale))


def _xy(extent: dict[str, float], size: tuple[int, int], lon: float, lat: float) -> tuple[float, float]:
    return (
        (lon - extent["west"]) / (extent["east"] - extent["west"]) * size[0],
        (extent["north"] - lat) / (extent["north"] - extent["south"]) * size[1],
    )


def _font(size: int) -> ImageFont.ImageFont:
    try:
        return ImageFont.load_default(size=size)
    except TypeError:  # very old Pillow
        return ImageFont.load_default()


def annotate(png: bytes, extent: dict[str, float], title: str, region_id: str | None = None, legend: list[tuple[str, tuple[int, int, int]]] | None = None) -> bytes:
    """Draw a lat/lon graticule, district labels, a title and a legend on a map PNG."""
    image = Image.open(io.BytesIO(png)).convert("RGB")
    size = image.size
    draw = ImageDraw.Draw(image, "RGBA")
    font, small = _font(15), _font(12)

    lon = np.ceil(extent["west"] * 2) / 2
    while lon <= extent["east"]:
        x, _ = _xy(extent, size, lon, extent["south"])
        draw.line([(x, 0), (x, size[1])], fill=(255, 255, 255, 45), width=1)
        draw.text((x + 2, size[1] - 14), f"{lon:.1f}E", fill=(255, 255, 255, 200), font=small)
        lon += 0.5
    lat = np.ceil(extent["south"] * 2) / 2
    while lat <= extent["north"]:
        _, y = _xy(extent, size, extent["west"], lat)
        draw.line([(0, y), (size[0], y)], fill=(255, 255, 255, 45), width=1)
        draw.text((3, y - 13), f"{lat:.1f}N", fill=(255, 255, 255, 200), font=small)
        lat += 0.5

    districts = json.loads(load_region(region_id).path("districts").read_text(encoding="utf-8"))
    box = (extent["west"], extent["south"], extent["east"], extent["north"])
    for feature in districts["features"]:
        geometry = shape(feature["geometry"])
        point = geometry.intersection(_box(box)).representative_point() if geometry.intersects(_box(box)) else None
        if point is not None and not point.is_empty:
            x, y = _xy(extent, size, point.x, point.y)
            draw.text((x - 28, y - 6), feature["properties"]["district"], fill=(255, 255, 255, 235), font=small, stroke_width=2, stroke_fill=(0, 0, 0, 255))

    draw.rectangle([0, 0, size[0], 24], fill=(0, 0, 0, 170))
    draw.text((6, 4), title, fill=(255, 255, 255, 255), font=font)
    if legend:
        y = 30
        for label, color in legend:
            draw.rectangle([6, y, 18, y + 12], fill=color + (255,))
            draw.text((24, y - 1), label, fill=(255, 255, 255, 255), font=small, stroke_width=2, stroke_fill=(0, 0, 0, 255))
            y += 18
    out = io.BytesIO()
    image.save(out, format="PNG")
    return out.getvalue()


def _box(bounds):
    from shapely.geometry import box

    return box(*bounds)


def screening_png(
    frame: pd.DataFrame, observed: pd.DataFrame, region_id: str | None = None, *, title: str = "Screening (v2 triage tier) and observed flooding"
) -> bytes:
    """Assets coloured by v2 triage tier; a cyan ring marks assets with an observed flood signal."""
    region = load_region(region_id)
    extent = region.extent
    size = _size(extent)
    image = Image.new("RGB", size, SEA)
    draw = ImageDraw.Draw(image, "RGBA")

    land = shape(json.loads(region.path("land_polygon").read_text(encoding="utf-8")))
    for polygon in getattr(land, "geoms", [land]):
        ring = [_xy(extent, size, x, y) for x, y in polygon.exterior.coords]
        draw.polygon(ring, fill=LAND)

    data = frame.merge(observed, on=["osm_element", "osm_id"], how="left")
    flooded = data[data["flooded"] == 1]
    for _, row in flooded.iterrows():
        x, y = _xy(extent, size, row["lon"], row["lat"])
        draw.ellipse([x - 6, y - 6, x + 6, y + 6], outline=FLOOD_RING + (255,), width=2)
    for _, row in data.iterrows():
        x, y = _xy(extent, size, row["lon"], row["lat"])
        color = TIER_COLORS.get(int(row.get("triage_tier", 4)), TIER_COLORS[4])
        draw.ellipse([x - 2.5, y - 2.5, x + 2.5, y + 2.5], fill=color + (230,))
    out = io.BytesIO()
    image.save(out, format="PNG")
    legend = [("tier 1 (top 10% relative risk)", TIER_COLORS[1]), ("tier 2", TIER_COLORS[2]), ("tier 3", TIER_COLORS[3]),
              ("tier 4", TIER_COLORS[4]), ("ring: observed flood signal", FLOOD_RING)]
    return annotate(out.getvalue(), extent, title, region_id, legend)


def earth_engine_maps(observed_flood: Any, region_id: str | None = None) -> dict[str, bytes]:
    """Flood-signal and rainfall maps rendered by Earth Engine, annotated."""
    import ee

    from services.earth_engine import land_mask, thumbnail_png
    from services.satellite_validation import EVENT

    region = load_region(region_id)
    extent = region.extent
    size = _size(extent)
    rect = [extent["west"], extent["south"], extent["east"], extent["north"]]
    dims = f"{size[0]}x{size[1]}"
    land = land_mask(region.country)

    def base():
        sea = ee.Image.constant(1).visualize(palette=["0e1e2e"], min=0, max=1)
        return sea.blend(land.visualize(palette=["3c3c3c"], min=0, max=1))

    # flood: mean over each display pixel keeps thin floods visible
    fraction = observed_flood.flood_image.unmask(0).toFloat().focalMean(300, "circle", "meters")
    flood_layer = fraction.updateMask(fraction.gt(0.01)).visualize(min=0, max=0.5, palette=["7fdcff", "1aa3ff", "0047ab"])
    flood_png = thumbnail_png(base().blend(flood_layer), rect, {}, dimensions=dims)

    rain = ee.ImageCollection("NASA/GPM_L3/IMERG_V07").select("precipitation").filterDate(*EVENT["rain"]).sum().multiply(0.5)
    rain_layer = rain.updateMask(land).visualize(min=0, max=450, palette=["f7fbff", "9ecae1", "3182bd", "756bb1", "d94801", "7f0000"])
    rain_png = thumbnail_png(base().blend(rain_layer), rect, {}, dimensions=dims)

    return {
        "flood": annotate(flood_png, extent, f"Observed flood signal ({observed_flood.sensor})", region_id,
                          [("flooded share of area (light to dark)", (26, 163, 255))]),
        "rain": annotate(rain_png, extent, f"Observed rain, IMERG {EVENT['rain'][0]} to {EVENT['rain'][1]} (mm)", region_id,
                         [("0 mm", (247, 251, 255)), ("about 200 mm", (117, 107, 177)), ("450 mm or more", (127, 0, 0))]),
    }
