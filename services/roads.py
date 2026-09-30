"""Road exposure: which main roads are likely to flood or be blocked, and which facilities that cuts off.

Main roads from OpenStreetMap (motorway, trunk, primary, secondary and tertiary, with their link roads) are cut
into sections of at most 1 km, split at every junction so the sections also form a routable network. Each
section is scored with the same hazards as the facilities, taken at its worst point rather than its centre:

    wet_ground     = max(exp(-HAND_min / 5 m), elevation_vulnerability(elevation_min), water_occurrence_max / 100)
    water_on_road  = max(surge_score, rain_score x (0.5 + 0.5 x wet_ground))
    flood level    = km-weighted relative bands: top 5% most exposed, next 15% high exposure, next 30% watch
    wind level     = modelled wind against the IMD damage bands: 62 km/h (branches), 89 km/h (avenue trees
                     uprooted, escape routes flooded), 118 km/h (road and rail traffic disrupted)
    level          = max(flood level, wind level): 0 open, 1 watch, 2 high exposure, 3 most exposed

HAND is MERIT Hydro's height above the nearest drainage line; elevation is SRTM; water occurrence is JRC; rain is
the GFS forecast issued at the cutoff; wind is the Holland profile; surge is the screening surge index.

Access: sections at level 3 are removed in a screening scenario. A non-hospital facility is "cut off" only when
it could reach a hospital before that removal and cannot afterwards. A hospital is cut off only when its remaining
component is small and contains no other hospital. Reachable facilities touching a level 2 or 3 road are "at risk".

Screening estimates for planning, not a traffic or hydraulic model: one-way rules, bridges' deck heights,
drainage capacity and local streets are not modelled.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from functools import lru_cache
from typing import Any, Iterable

import numpy as np
import pandas as pd

from services.hazards.coast import haversine_matrix_km
from services.hazards.rainfall import rain_flood_score

MODEL_VERSION = "roads-1.0"
MAX_SECTION_KM = 1.0
HAND_SCALE_M = 5.0
WIND_CUTS_KMH = (62.0, 89.0, 118.0)
# Sentinel-2 validation bands: observed standing-water share rises across all four levels.
# The upper band is deliberately stringent; see docs/ROAD_EXPOSURE.md for the validation and limits.
FLOOD_PERCENTILES = (0.50, 0.80, 0.95)
SNAP_KM = 2.0
ISLAND_KM = 25.0
HOSPITAL_SEARCH_KM = 80.0
LEVEL_NAMES = ("open", "watch", "high_exposure", "most_exposed")
HIGHWAY_CLASSES = ("motorway", "trunk", "primary", "secondary", "tertiary")
HIGHWAY_RANK = {name: i for i, name in enumerate(HIGHWAY_CLASSES)}
LABEL = "Relative road exposure screening for this storm, not a traffic, operational-status or hydraulic model."


def highway_class(tag: str) -> str | None:
    """'primary_link' -> 'primary'; anything outside the main-road classes -> None."""
    base = tag.removesuffix("_link")
    return base if base in HIGHWAY_RANK else None


# ---------------------------------------------------------------- sections

def _step_km(coords: np.ndarray) -> np.ndarray:
    lon, lat = coords[:, 0], coords[:, 1]
    p1, p2 = np.radians(lat[:-1]), np.radians(lat[1:])
    dphi, dlmb = p2 - p1, np.radians(lon[1:] - lon[:-1])
    a = np.sin(dphi / 2) ** 2 + np.cos(p1) * np.cos(p2) * np.sin(dlmb / 2) ** 2
    return 2 * 6371.0088 * np.arcsin(np.sqrt(np.clip(a, 0, 1)))


def _key(x: float, y: float) -> tuple[float, float]:
    return (round(x, 7), round(y, 7))


@dataclass
class Way:
    way_id: int
    highway: str
    name: str | None
    ref: str | None
    coords: np.ndarray  # (n, 2) lon, lat


def split_ways(ways: Iterable[Way], max_km: float = MAX_SECTION_KM) -> pd.DataFrame:
    """Cut ways at junctions (vertices shared with another way) and then into pieces of at most ``max_km``.

    A single straight span longer than ``max_km`` is kept whole. Returns one row per section with its
    coordinates, length, end-node keys and midpoint.
    """
    ways = [w for w in ways if len(w.coords) >= 2]
    use = Counter(_key(x, y) for w in ways for x, y in w.coords)
    rows: list[dict[str, Any]] = []
    for w in ways:
        steps = _step_km(w.coords)
        start, run, k = 0, 0.0, 0
        for i in range(1, len(w.coords)):
            run += steps[i - 1]
            last = i == len(w.coords) - 1
            if last or use[_key(*w.coords[i])] > 1 or run >= max_km:
                piece = w.coords[start : i + 1]
                rows.append({
                    "section_id": f"{w.way_id}:{k}", "way_id": w.way_id, "highway": w.highway,
                    "name": w.name, "ref": w.ref, "coords": piece, "length_km": float(run),
                    "a": _key(*piece[0]), "b": _key(*piece[-1]),
                })
                start, run, k = i, 0.0, k + 1
    frame = pd.DataFrame(rows)
    if frame.empty:
        return frame
    mids = [_midpoint(c) for c in frame["coords"]]
    frame["mid_lon"] = [m[0] for m in mids]
    frame["mid_lat"] = [m[1] for m in mids]
    return frame


def _midpoint(coords: np.ndarray) -> tuple[float, float]:
    steps = _step_km(coords)
    half = steps.sum() / 2
    if half <= 0:
        return float(coords[0, 0]), float(coords[0, 1])
    cum = np.cumsum(steps)
    i = int(np.searchsorted(cum, half))
    before = cum[i - 1] if i else 0.0
    f = (half - before) / steps[i] if steps[i] > 0 else 0.0
    p = coords[i] + f * (coords[i + 1] - coords[i])
    return float(p[0]), float(p[1])


# ---------------------------------------------------------------- hazard scoring

def elevation_vulnerability(elevation_m: np.ndarray) -> np.ndarray:
    """1 at or below 5 m, falling linearly to 0 at 30 m (the facility model's terrain curve)."""
    return np.clip((30.0 - np.asarray(elevation_m, float)) / 25.0, 0.0, 1.0)


def wet_ground(hand_min_m: np.ndarray, elevation_min_m: np.ndarray, water_max_pct: np.ndarray) -> np.ndarray:
    hand = np.exp(-np.clip(np.nan_to_num(np.asarray(hand_min_m, float), nan=HAND_SCALE_M * 6), 0.0, None) / HAND_SCALE_M)
    elev = elevation_vulnerability(np.nan_to_num(np.asarray(elevation_min_m, float), nan=30.0))
    water = np.clip(np.nan_to_num(np.asarray(water_max_pct, float), nan=0.0) / 100.0, 0.0, 1.0)
    return np.maximum.reduce([hand, elev, water])


def cut_level(values: np.ndarray, cuts: tuple[float, float, float]) -> np.ndarray:
    v = np.nan_to_num(np.asarray(values, float), nan=0.0)
    return (v >= cuts[0]).astype(int) + (v >= cuts[1]).astype(int) + (v >= cuts[2]).astype(int)


def weighted_percentile_cuts(values: np.ndarray, weights: np.ndarray) -> tuple[float, float, float]:
    """Km-weighted 50th, 80th and 95th percentiles; equal scores stay in the lower band."""
    v, w = np.asarray(values, float), np.asarray(weights, float)
    good = np.isfinite(v) & np.isfinite(w) & (w > 0)
    if not good.any():
        return (0.0, 0.0, 0.0)
    order = np.argsort(v[good], kind="stable")
    sv, sw = v[good][order], w[good][order]
    cumulative = np.cumsum(sw)
    return tuple(float(sv[min(np.searchsorted(cumulative, q * cumulative[-1], side="left"), len(sv) - 1)])
                 for q in FLOOD_PERCENTILES)


def relative_level(values: np.ndarray, weights: np.ndarray, tie_breaker: np.ndarray | None = None) -> tuple[np.ndarray, tuple[float, float, float]]:
    cuts = weighted_percentile_cuts(values, weights)
    v = np.nan_to_num(np.asarray(values, float), nan=0.0)
    w = np.nan_to_num(np.asarray(weights, float), nan=0.0)
    tie = np.arange(len(v)).astype(str) if tie_breaker is None else np.asarray(tie_breaker).astype(str)
    order = np.lexsort((tie, v))
    ranked_w = np.maximum(w[order], 0.0)
    cumulative = np.cumsum(ranked_w)
    midrank = (cumulative - ranked_w / 2) / cumulative[-1] if cumulative[-1] else np.zeros(len(v))
    ranked_level = sum((midrank > q).astype(int) for q in FLOOD_PERCENTILES)
    level = np.empty(len(v), dtype=int)
    level[order] = ranked_level
    return level, cuts


def score_sections(frame: pd.DataFrame) -> pd.DataFrame:
    """Add wet_ground, water_on_road, flood/wind levels, the level and its main cause.

    Needs ``hand_min_m, elevation_min_m, water_max_pct, rain_mm, wind_kmh, surge_score``.
    """
    out = frame.copy()
    out["wet_ground"] = np.round(wet_ground(out["hand_min_m"], out["elevation_min_m"], out["water_max_pct"]), 4)
    rain_part = rain_flood_score(out["rain_mm"].fillna(0.0).to_numpy(), out["wet_ground"].to_numpy())
    surge = out["surge_score"].fillna(0.0).to_numpy(float)
    out["water_on_road"] = np.round(np.maximum(surge, rain_part), 4)
    weights = out["length_km"].to_numpy(float) if "length_km" in out else np.ones(len(out))
    tie = out["section_id"].to_numpy() if "section_id" in out else np.arange(len(out))
    out["flood_level"], out.attrs["flood_score_cuts"] = relative_level(out["water_on_road"], weights, tie)
    out["wind_level"] = cut_level(out["wind_kmh"], WIND_CUTS_KMH)
    out["level"] = np.maximum(out["flood_level"], out["wind_level"])
    cause = np.where(surge >= rain_part, "surge", "flood")
    out["cause"] = np.where(out["level"] == 0, "none", np.where(out["wind_level"] > out["flood_level"], "wind", cause))
    return out


# ---------------------------------------------------------------- network and access

def build_graph(sections: pd.DataFrame, *, skip_level: int | None = None):
    """Undirected road graph weighted by length. Sections at ``skip_level`` or above are left out for screening."""
    import networkx as nx

    graph = nx.Graph()
    graph.add_nodes_from(set(sections["a"]) | set(sections["b"]))
    for a, b, km, level in zip(sections["a"], sections["b"], sections["length_km"], sections["level"]):
        if a == b or (skip_level is not None and level >= skip_level):
            continue
        if not graph.has_edge(a, b) or graph[a][b]["km"] > km:
            graph.add_edge(a, b, km=float(km), level=int(level))
    return graph


def _component_km(graph) -> dict[Any, float]:
    import networkx as nx

    size: dict[Any, float] = {}
    for nodes in nx.connected_components(graph):
        km = float(sum(d["km"] for _, _, d in graph.subgraph(nodes).edges(data=True)))
        for n in nodes:
            size[n] = km
    return size


def snap(nodes: list[tuple[float, float]], lon: np.ndarray, lat: np.ndarray) -> tuple[list[Any], np.ndarray]:
    """Nearest network node for each point and the distance to it (km)."""
    import shapely
    from shapely.strtree import STRtree

    tree = STRtree(shapely.points(np.array(nodes)))
    idx = tree.query_nearest(shapely.points(np.column_stack([lon, lat])), return_distance=False, all_matches=False)[1]
    hit = np.array(nodes)[idx]
    km = np.array([haversine_matrix_km(np.array([la]), np.array([lo]), np.array([h[1]]), np.array([h[0]]))[0, 0]
                   for lo, la, h in zip(lon, lat, hit)])
    return [nodes[i] for i in idx], km


def _nearest_hospital_km(graph, sources: list[Any]) -> dict[Any, float]:
    import networkx as nx

    present = [s for s in set(sources) if s in graph]
    if not present:
        return {}
    return nx.multi_source_dijkstra_path_length(graph, present, cutoff=HOSPITAL_SEARCH_KM, weight="km")


def access(sections: pd.DataFrame, facilities: pd.DataFrame, hospital_mask: pd.Series) -> pd.DataFrame:
    """Per facility: screened road access and hospital distance before and after removing level 3 sections.

    ``facilities`` needs ``osm_element, osm_id, lat, lon``; ``hospital_mask`` marks the hospitals to route to.
    """
    intact = build_graph(sections)
    closed = build_graph(sections, skip_level=3)
    nodes = list(intact.nodes)
    node, snap_km = snap(nodes, facilities["lon"].to_numpy(float), facilities["lat"].to_numpy(float))
    island = _component_km(closed)
    worst_touching = {n: 0 for n in nodes}
    for a, b, level in zip(sections["a"], sections["b"], sections["level"]):
        worst_touching[a] = max(worst_touching[a], int(level))
        worst_touching[b] = max(worst_touching[b], int(level))

    hospital_nodes = [n for n, is_h, km in zip(node, hospital_mask.to_numpy(bool), snap_km) if is_h and km <= SNAP_KM]
    before = _nearest_hospital_km(intact, hospital_nodes)
    after = _nearest_hospital_km(closed, hospital_nodes)
    hospital_count: dict[Any, int] = {}
    import networkx as nx
    for component in nx.connected_components(closed):
        count = sum(n in component for n in hospital_nodes)
        for n in component:
            hospital_count[n] = count

    out = facilities[["osm_element", "osm_id"]].reset_index(drop=True).copy()
    status, km_before, km_after = [], [], []
    for n, km, is_h in zip(node, snap_km, hospital_mask.to_numpy(bool)):
        if km > SNAP_KM:
            status.append("not_assessed")
            km_before.append(None)
            km_after.append(None)
            continue
        if is_h and hospital_count.get(n, 0) <= 1 and island.get(n, 0.0) < ISLAND_KM:
            status.append("cut_off")
        elif not is_h and n in before and n not in after:
            status.append("cut_off")
        elif n in after and worst_touching.get(n, 0) >= 2:
            status.append("at_risk")
        else:
            status.append("open")
        km_before.append(round(before[n] + km, 1) if n in before else None)
        km_after.append(round(after[n] + km, 1) if n in after else None)
    out["road_access"] = status
    out["road_snap_km"] = np.round(snap_km, 2)
    out["hospital_km_before"] = km_before
    out["hospital_km_after"] = km_after
    return out


# ---------------------------------------------------------------- cached outputs (runtime)

ACCESS_COLUMNS = ["road_access", "hospital_km_before", "hospital_km_after"]


def load_summary(region_id: str | None = None) -> dict[str, Any] | None:
    import json

    from services.config import load_region

    region = load_region(region_id)
    try:
        path = region.path("roads_summary")
    except KeyError:
        return None
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def load_access(region_id: str | None = None) -> pd.DataFrame | None:
    from services.config import load_region

    region = load_region(region_id)
    try:
        path = region.path("road_access")
    except KeyError:
        return None
    return pd.read_csv(path) if path.exists() else None


def with_access(frame: pd.DataFrame, region_id: str | None = None) -> pd.DataFrame:
    """Add the road-access columns to an assets frame (unchanged when the region has no road layer)."""
    table = load_access(region_id)
    if table is None or frame.empty:
        return frame
    return frame.drop(columns=[c for c in ACCESS_COLUMNS if c in frame.columns]).merge(
        table[["osm_element", "osm_id", *ACCESS_COLUMNS]], on=["osm_element", "osm_id"], how="left")


ROUTE_MATCH_DEG = 0.0003  # about 30 m: a route point this close to a scored section is taken to be on it
ROUTE_STEP_KM = 0.05


@lru_cache(maxsize=4)
def _risky_sections(region_id: str | None):
    """Shapely lines and levels of the sections at level 2 or above, from the web payload."""
    import gzip
    import json

    import shapely
    from shapely.strtree import STRtree

    from services.config import load_region

    path = load_region(region_id).paths.get("roads_web")
    if path is None or not path.exists():
        return None
    with gzip.open(path, "rt", encoding="utf-8") as fh:
        data = json.load(fh)
    coords = np.asarray(data["path"], float).reshape(-1, 2)
    ends = [*data["starts"][1:], len(coords)]
    keep = [i for i, level in enumerate(data["level"]) if level >= 2]
    lines = [shapely.linestrings(coords[data["starts"][i] : ends[i]]) for i in keep if ends[i] - data["starts"][i] >= 2]
    levels = np.array([data["level"][i] for i in keep if ends[i] - data["starts"][i] >= 2])
    return STRtree(lines), levels


def route_exposure(points: list[tuple[float, float]], region_id: str | None = None) -> dict[str, float] | None:
    """Km of a route on most-exposed (level 3) and high-exposure (level 2) sections. None without a road layer."""
    import shapely

    risky = _risky_sections(region_id)
    if risky is None or len(points) < 2:
        return None
    tree, levels = risky
    line = np.array([(lon, lat) for lat, lon in points], float)
    steps = _step_km(line)
    dense = [line[0]]
    for (a, b), km in zip(zip(line[:-1], line[1:]), steps):
        n = max(1, int(np.ceil(km / ROUTE_STEP_KM)))
        dense.extend(a + (b - a) * (k / n) for k in range(1, n + 1))
    dense = np.asarray(dense)
    step = _step_km(dense)
    mid = shapely.points((dense[:-1] + dense[1:]) / 2)
    hit_pt, hit_line = tree.query_nearest(mid, max_distance=ROUTE_MATCH_DEG, all_matches=False)
    worst = np.zeros(len(mid), int)
    np.maximum.at(worst, hit_pt, levels[hit_line])
    return {"km_most_exposed": round(float(step[worst >= 3].sum()), 2),
            "km_high_exposure": round(float(step[worst == 2].sum()), 2)}


def road_status(district: str | None = None, region_id: str | None = None, top: int = 10) -> dict[str, Any] | None:
    """Km by level and the worst named roads, for the corridor or one district. None without a road layer."""
    from services.config import load_region

    path = load_region(region_id).paths.get("road_sections")
    if path is None or not path.exists():
        return None
    frame = pd.read_csv(path)
    if district:
        frame = frame[frame["district"].fillna("").str.lower() == district.strip().lower()]
        if frame.empty:
            raise KeyError(district)
    risky = frame[(frame["level"] >= 2) & frame["label"].notna()]
    worst = (risky.groupby("label").agg(km=("length_km", "sum"), level=("level", "max"), highway=("highway", "first"))
             .sort_values(["level", "km"], ascending=False).head(top))
    return {
        "district": district, "km_total": round(float(frame["length_km"].sum()), 1), "km_by_level": km_by_level(frame),
        "km_level2plus_by_cause": {str(k): round(float(v), 1) for k, v in frame[frame["level"] >= 2].groupby("cause")["length_km"].sum().items()},
        "worst_roads": [{"road": k, "km": round(float(r.km), 1), "level": LEVEL_NAMES[int(r.level)], "highway": r.highway} for k, r in worst.iterrows()],
        "label": LABEL,
    }


# ---------------------------------------------------------------- summaries

def km_by_level(frame: pd.DataFrame) -> dict[str, float]:
    return {LEVEL_NAMES[i]: round(float(frame.loc[frame["level"] == i, "length_km"].sum()), 1) for i in range(4)}


def road_label(name: Any, ref: Any) -> str | None:
    name = None if name is None or (isinstance(name, float) and np.isnan(name)) else str(name)
    ref = None if ref is None or (isinstance(ref, float) and np.isnan(ref)) else str(ref)
    if name and ref and ref not in name:
        return f"{ref} · {name}"
    return name or ref


__all__ = [
    "Way", "split_ways", "score_sections", "build_graph", "access", "km_by_level", "road_label",
    "highway_class", "MODEL_VERSION", "LEVEL_NAMES", "FLOOD_PERCENTILES", "WIND_CUTS_KMH", "LABEL",
]
