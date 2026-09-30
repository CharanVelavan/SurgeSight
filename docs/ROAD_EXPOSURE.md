# Road exposure

SurgeSight screens about 34,000 km of OpenStreetMap motorway, trunk, primary, secondary and tertiary roads, including link roads, in the Cyclone Michaung study area. It is a planning screen, not a statement of road status.

## Model and fixed relative bands

Ways are split at junctions and into sections of about 1 km. Each section uses the lowest SRTM elevation, lowest MERIT Hydro height above drainage, highest JRC surface-water occurrence, NOAA GFS forecast rain available at the bulletin cutoff, Holland-profile wind and the SurgeSight coastal-surge screen.

The flood score is `max(surge_score, rain_score × (0.5 + 0.5 × wet_ground))`. This is the non-saturating rain–terrain interaction used by the facility model. Absolute cut-offs saturated on the coastal plain because forecast rain was high and most section minima were below 30 m.

The design is fixed before validation: km-weighted score percentiles mark the top 5% of road kilometres as **most exposed**, the next 15% as **high exposure**, the next 30% as **watch**, and the lower half as **lower exposure**. Weighted mid-ranks are used; equal scores are assigned deterministically by section ID so a large tied group cannot erase or greatly inflate a band. Absolute IMD wind bands at 62, 89 and 118 km/h can raise a section's final level. These relative bands always highlight the worst part of any storm's assessed network; they do not establish whether a road is usable.

## Access screen

The most-exposed sections are removed from an approximate undirected network. A non-hospital facility is marked `cut_off` only if it could reach a hospital within the 80 km search before that removal and cannot afterwards. A hospital is marked `cut_off` only when its remaining component has less than 25 km of assessed road and contains no other road-connected hospital. A facility that remains connected and touches a high-exposure or most-exposed section is `at_risk`. Facilities more than 2 km from the assessed network are `not_assessed`.

## Validation

Validation values are written by `scripts/build_roads.py` to `data/processed/roads/roads_summary.json`. Sentinel-2 standing water is used only as an observed proxy, never as a model input. The current AUC and by-level shares are reported below after each rebuild. Weak skill must be read plainly: the comparable facility flood-ranking AUCs are about 0.55–0.62, and this road screen is for triage, not prediction.

<!-- ROAD_VALIDATION -->

For the current Michaung build, 33,929.7 km was assessed. The final levels, after the absolute wind bands can raise the relative flood level, are: 5,375.9 km lower exposure, 14,362.3 km watch, 12,494.8 km high exposure and 1,696.7 km most exposed. The most-exposed share is 5.0%. High exposure or above is 41.8%; the 89 km/h absolute wind band alone covers about a quarter of assessed kilometres, so the final combined share is higher than the flood-score design's 20%.

Sentinel-2 observed 25,481.1 km across 45,278 sections. The road score AUC is **0.549**, which is weak ranking skill. Observed standing-water shares rise from 10.1% for lower exposure to 11.6% for watch, 11.9% for high exposure and 20.4% for most exposed. The most-exposed band separates most clearly. These results are reported without post-validation adjustment to the fixed percentile design.

The access screen flags 418 of 4,214 facilities as `cut_off` (9.9%) in the approximate network-removal scenario. Counts are: 108 hospitals, 166 schools, 43 shelters, 61 substations, 21 police stations, 8 fire stations, 7 water facilities and 4 fishing harbours. This is not a confirmed access or road-status count; the lack of local streets and bridge information makes network fragmentation especially uncertain.

## Limits

- Screening only; field reports and responsible authorities must determine road status and routing.
- Main roads only, not local streets.
- No bridge deck heights, drainage capacity, one-way rules or live traffic.
- The network after removing most-exposed sections is an approximation.
- Sentinel-2 is an optical proxy with cloud gaps and under-detection of urban flooding.
- Relative levels always identify a most-exposed share, even in a weak storm.
- Hindi, Tamil, Telugu, Bengali and Odia road copy still needs native-speaker review.

The source tables are rebuilt with `.venv/bin/python scripts/build_roads.py`. Earth Engine terrain, rain and Sentinel-2 samples are cached stage by stage in the ignored `data/raw/road_samples.csv`.
