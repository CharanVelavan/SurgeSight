import json
import sys
from pathlib import Path

import ee

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from services.earth_engine import init_ee, land_mask as india_land_mask


OUTPUT = Path("data/processed/michaung_terrain_summary.json")


def main():
    print("Initializing Earth Engine...")
    init_ee()

    # =========================================================
    # MICHAUNG DEMO REGION
    #
    # Chennai + northern Tamil Nadu + southern Andhra Pradesh
    # =========================================================

    region = ee.Geometry.Rectangle(
        [
            79.0,   # west
            11.5,   # south
            82.0,   # east
            15.0,   # north
        ]
    )

    print("Loading Earth Engine datasets...")

    # =========================================================
    # 1. SRTM ELEVATION
    # =========================================================

    elevation = (
        ee.Image("USGS/SRTMGL1_003")
        .select("elevation")
        .rename("elevation")
    )

    # SRTM reports 0 m over open water, which inflated the low-lying share
    # (K3). Restrict every statistic to India's land polygon (LSIB).
    land_mask = india_land_mask("India")
    elevation = elevation.updateMask(land_mask)

    # =========================================================
    # 2. JRC GLOBAL SURFACE WATER
    #
    # IMPORTANT:
    # occurrence has masked pixels.
    #
    # For vulnerability screening, pixels with no recorded
    # surface-water occurrence should behave as 0 rather than
    # disappear from the final calculation.
    # =========================================================

    water_raw = (
        ee.Image("JRC/GSW1_4/GlobalSurfaceWater")
        .select("occurrence")
    )

    water = (
        water_raw
        .unmask(0)
        .updateMask(land_mask)
        .rename("water_occurrence")
    )

    # =========================================================
    # 3. WORLDPOP
    #
    # Restrict explicitly to India.
    #
    # Then automatically use the newest year available in the
    # Earth Engine WorldPop collection.
    # =========================================================

    print("Searching WorldPop population images for India...")

    population_collection_all = (
        ee.ImageCollection("WorldPop/GP/100m/pop")
        .filter(
            ee.Filter.eq(
                "country",
                "IND"
            )
        )
        .filterBounds(region)
    )

    population_total_images = (
        population_collection_all
        .size()
        .getInfo()
    )

    print(
        "Indian WorldPop images intersecting region:",
        population_total_images,
    )

    if population_total_images == 0:
        raise RuntimeError(
            "No Indian WorldPop images intersect "
            "the Michaung demo region."
        )

    years_raw = (
        population_collection_all
        .aggregate_array("year")
        .getInfo()
    )

    years = sorted(
        {
            int(year)
            for year in years_raw
            if year is not None
        }
    )

    print(
        "Indian WorldPop years available:",
        years,
    )

    if not years:
        raise RuntimeError(
            "WorldPop returned images but no valid "
            "year metadata."
        )

    population_year = max(years)

    print(
        "Using WorldPop year:",
        population_year,
    )

    population_collection = (
        population_collection_all
        .filter(
            ee.Filter.eq(
                "year",
                population_year,
            )
        )
    )

    population_image_count = (
        population_collection
        .size()
        .getInfo()
    )

    print(
        "Population images selected:",
        population_image_count,
    )

    population = (
        population_collection
        .select("population")
        .mosaic()
        .rename("population")
    )

    population_bands = (
        population
        .bandNames()
        .getInfo()
    )

    print(
        "Population bands:",
        population_bands,
    )

    if "population" not in population_bands:
        raise RuntimeError(
            "WorldPop population band not found."
        )

    # =========================================================
    # 4. TERRAIN VULNERABILITY MASKS
    # =========================================================

    print("Building terrain screening layers...")

    # Land <= 10 metres
    low_lying = (
        elevation
        .lte(10)
        .rename("low_lying")
    )

    # Land <= 5 metres
    very_low = (
        elevation
        .lte(5)
        .rename("very_low")
    )

    # Historical water occurrence >= 10%
    water_presence = (
        water
        .gte(10)
        .rename("water_presence")
    )

    # =========================================================
    # 5. FLOOD SUSCEPTIBILITY SCREEN
    #
    # Prototype screening index:
    #
    # Low elevation         60%
    # Very low elevation    25%
    # Surface-water history 15%
    #
    # Range: 0 → 1
    #
    # This is NOT a hydrodynamic flood model.
    # =========================================================

    flood_screen = (
        low_lying
        .multiply(0.60)
        .add(
            very_low.multiply(0.25)
        )
        .add(
            water_presence.multiply(0.15)
        )
        .clamp(0, 1)
        .rename("flood_screen")
    )

    # =========================================================
    # 6. COMPUTE STATISTICS
    # =========================================================

    print("Computing elevation statistics...")

    elevation_stats = (
        elevation.reduceRegion(
            reducer=ee.Reducer.mean(),
            geometry=region,
            scale=90,
            maxPixels=1_000_000_000,
            bestEffort=True,
        )
        .getInfo()
    )

    print("Computing low-lying terrain percentage...")

    low_lying_stats = (
        low_lying.reduceRegion(
            reducer=ee.Reducer.mean(),
            geometry=region,
            scale=100,
            maxPixels=1_000_000_000,
            bestEffort=True,
        )
        .getInfo()
    )

    print("Computing very-low terrain percentage...")

    very_low_stats = (
        very_low.reduceRegion(
            reducer=ee.Reducer.mean(),
            geometry=region,
            scale=100,
            maxPixels=1_000_000_000,
            bestEffort=True,
        )
        .getInfo()
    )

    print("Computing surface-water exposure...")

    water_presence_stats = (
        water_presence.reduceRegion(
            reducer=ee.Reducer.mean(),
            geometry=region,
            scale=100,
            maxPixels=1_000_000_000,
            bestEffort=True,
        )
        .getInfo()
    )

    water_occurrence_stats = (
        water.reduceRegion(
            reducer=ee.Reducer.mean(),
            geometry=region,
            scale=100,
            maxPixels=1_000_000_000,
            bestEffort=True,
        )
        .getInfo()
    )

    print("Computing flood susceptibility...")

    flood_stats = (
        flood_screen.reduceRegion(
            reducer=ee.Reducer.mean(),
            geometry=region,
            scale=100,
            maxPixels=1_000_000_000,
            bestEffort=True,
        )
        .getInfo()
    )

    print("Computing population estimate...")

    population_stats = (
        population.reduceRegion(
            reducer=ee.Reducer.sum(),
            geometry=region,
            scale=100,
            maxPixels=1_000_000_000,
            bestEffort=True,
        )
        .getInfo()
    )

    # =========================================================
    # 7. EXTRACT VALUES
    # =========================================================

    mean_elevation = elevation_stats.get(
        "elevation"
    )

    low_lying_fraction = low_lying_stats.get(
        "low_lying"
    )

    very_low_fraction = very_low_stats.get(
        "very_low"
    )

    water_presence_fraction = (
        water_presence_stats.get(
            "water_presence"
        )
    )

    mean_water_occurrence = (
        water_occurrence_stats.get(
            "water_occurrence"
        )
    )

    mean_flood_screen = flood_stats.get(
        "flood_screen"
    )

    population_estimate = (
        population_stats.get(
            "population"
        )
    )

    # =========================================================
    # 8. CONVERT TO HUMAN-READABLE VALUES
    # =========================================================

    def percentage(value):
        if value is None:
            return None

        return value * 100

    low_lying_percentage = percentage(
        low_lying_fraction
    )

    very_low_percentage = percentage(
        very_low_fraction
    )

    water_presence_percentage = percentage(
        water_presence_fraction
    )

    if population_estimate is not None:
        population_estimate = int(
            round(
                population_estimate
            )
        )

    # =========================================================
    # 9. CONSISTENCY CHECK
    #
    # Since:
    #
    # flood =
    # 0.60 * low +
    # 0.25 * very_low +
    # 0.15 * water
    #
    # the mean should approximately equal the same weighted
    # combination of the three mean masks.
    # =========================================================

    expected_mean_flood_screen = None

    if (
        low_lying_fraction is not None
        and very_low_fraction is not None
        and water_presence_fraction is not None
    ):
        expected_mean_flood_screen = (
            0.60 * low_lying_fraction
            + 0.25 * very_low_fraction
            + 0.15 * water_presence_fraction
        )

    # =========================================================
    # 10. BUILD OUTPUT
    # =========================================================

    previous_summary = None
    if OUTPUT.exists():
        previous = json.loads(OUTPUT.read_text(encoding="utf-8"))
        previous_summary = previous.get("previous_unmasked_summary") or (
            None if previous.get("land_mask") else previous.get("summary")
        )

    result = {
        "land_mask": {
            "dataset": "USDOS/LSIB_SIMPLE/2017",
            "country": "India",
            "note": "All statistics are computed over India land pixels only.",
        },
        "previous_unmasked_summary": previous_summary,

        "scenario": {
            "name": "Cyclone Michaung",
            "year": 2023,
            "country": "India",
        },

        "region": {
            "west": 79.0,
            "south": 11.5,
            "east": 82.0,
            "north": 15.0,
        },

        "datasets": {
            "elevation": {
                "id": "USGS/SRTMGL1_003",
            },

            "surface_water": {
                "id": (
                    "JRC/GSW1_4/"
                    "GlobalSurfaceWater"
                ),
                "band": "occurrence",
            },

            "population": {
                "id": (
                    "WorldPop/GP/100m/pop"
                ),
                "country": "IND",
                "year": population_year,
            },
        },

        "summary": {
            "mean_elevation_m":
                mean_elevation,

            "low_lying_percentage":
                low_lying_percentage,

            "very_low_percentage":
                very_low_percentage,

            "water_presence_percentage":
                water_presence_percentage,

            "mean_surface_water_occurrence_pct":
                mean_water_occurrence,

            "mean_flood_screen":
                mean_flood_screen,

            "expected_mean_flood_screen":
                expected_mean_flood_screen,

            "population_estimate":
                population_estimate,
        },

        "screening_model": {
            "low_lying_threshold_m": 10,

            "very_low_threshold_m": 5,

            "water_occurrence_threshold_pct": 10,

            "weights": {
                "low_lying": 0.60,
                "very_low": 0.25,
                "surface_water": 0.15,
            },

            "description": (
                "Screening-level flood vulnerability "
                "indicator combining terrain elevation "
                "and historical surface-water occurrence."
            ),

            "warning": (
                "This prototype does not replace "
                "operational hydrodynamic flood or "
                "storm-surge modelling."
            ),
        },
    }

    # =========================================================
    # 11. SAVE
    # =========================================================

    OUTPUT.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    with OUTPUT.open(
        "w",
        encoding="utf-8",
    ) as file:
        json.dump(
            result,
            file,
            indent=2,
        )

    # =========================================================
    # 12. OUTPUT
    # =========================================================

    print()
    print(
        "============================================"
    )

    print(
        "SURGESIGHT_TERRAIN_OK"
    )


    print(
        "============================================"
    )

    print()

    print(
        f"WorldPop country: IND"
    )

    print(
        f"WorldPop year: {population_year}"
    )

    if population_estimate is not None:
        print(
            f"Estimated population: "
            f"{population_estimate:,}"
        )

    if mean_elevation is not None:
        print(
            f"Mean elevation: "
            f"{mean_elevation:.2f} m"
        )

    if low_lying_percentage is not None:
        print(
            f"Low-lying terrain <=10m: "
            f"{low_lying_percentage:.2f}%"
        )

    if very_low_percentage is not None:
        print(
            f"Very-low terrain <=5m: "
            f"{very_low_percentage:.2f}%"
        )

    if water_presence_percentage is not None:
        print(
            f"Historical water-prone land: "
            f"{water_presence_percentage:.2f}%"
        )

    if mean_flood_screen is not None:
        print(
            f"Mean flood screen: "
            f"{mean_flood_screen:.4f}"
        )

    if expected_mean_flood_screen is not None:
        print(
            f"Expected weighted mean: "
            f"{expected_mean_flood_screen:.4f}"
        )

    print()
    print(
        "Saved:",
        OUTPUT,
    )
    print()


if __name__ == "__main__":
    main()