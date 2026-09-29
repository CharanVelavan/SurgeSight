from pathlib import Path
import pandas as pd

INPUT = Path("data/raw/ibtracs.csv")
OUTPUT = Path("data/processed/michaung_track.csv")

print("Loading IBTrACS...")

# IBTrACS CSV has a second row containing units.
df = pd.read_csv(INPUT, skiprows=[1], low_memory=False)

df["NAME"] = df["NAME"].astype(str).str.upper().str.strip()
df["SEASON"] = pd.to_numeric(df["SEASON"], errors="coerce")

storm = df[
    (df["SEASON"] == 2023)
    & (df["NAME"] == "MICHAUNG")
].copy()

if storm.empty:
    raise RuntimeError("Cyclone MICHAUNG 2023 not found in IBTrACS")

storm["LAT"] = pd.to_numeric(storm["LAT"], errors="coerce")
storm["LON"] = pd.to_numeric(storm["LON"], errors="coerce")
storm["WMO_WIND"] = pd.to_numeric(
    storm.get("WMO_WIND"), errors="coerce"
)
storm["WMO_PRES"] = pd.to_numeric(
    storm.get("WMO_PRES"), errors="coerce"
)

# Use agency alternatives if WMO fields are missing.
if "USA_WIND" in storm.columns:
    usa_wind = pd.to_numeric(storm["USA_WIND"], errors="coerce")
    storm["WIND_KT"] = storm["WMO_WIND"].fillna(usa_wind)
else:
    storm["WIND_KT"] = storm["WMO_WIND"]

if "USA_PRES" in storm.columns:
    usa_pres = pd.to_numeric(storm["USA_PRES"], errors="coerce")
    storm["PRESSURE_HPA"] = storm["WMO_PRES"].fillna(usa_pres)
else:
    storm["PRESSURE_HPA"] = storm["WMO_PRES"]

storm["ISO_TIME"] = pd.to_datetime(storm["ISO_TIME"], errors="coerce")

storm = storm[
    [
        "SID",
        "NAME",
        "ISO_TIME",
        "LAT",
        "LON",
        "WIND_KT",
        "PRESSURE_HPA",
        "BASIN",
    ]
].dropna(subset=["LAT", "LON", "ISO_TIME"])

storm = storm.sort_values("ISO_TIME").drop_duplicates(
    subset=["ISO_TIME", "LAT", "LON"]
)

storm["WIND_KMH"] = storm["WIND_KT"] * 1.852

OUTPUT.parent.mkdir(parents=True, exist_ok=True)
storm.to_csv(OUTPUT, index=False)

print()
print("SURGESIGHT_MICHAUNG_OK")
print("Track points:", len(storm))
print("Start:", storm["ISO_TIME"].min())
print("End:", storm["ISO_TIME"].max())
print()
print(
    storm[
        ["ISO_TIME", "LAT", "LON", "WIND_KMH", "PRESSURE_HPA"]
    ].tail(10).to_string(index=False)
)
print()
print("Saved:", OUTPUT)
