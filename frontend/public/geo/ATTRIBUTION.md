# Attribution — public/geo/india-states.geojson

Source: **"india-maps-data" by udit-001** — https://github.com/udit-001/india-maps-data
File: `geojson/india.geojson` (district-level, 760 features)

Processing (this repo, 2026-09-22): dissolved 760 district polygons into 36
state/UT features (`mapshaper -dissolve fields=st_nm -simplify 8% keep-shapes`),
coordinate precision truncated to 5 decimals. Output: 28 KB, Polygon/MultiPolygon,
property `st_nm` = state name.

Upstream license: the upstream repository declares **no license file** (as of
2026-09-22). Map geometry of India is used here under the general understanding
that government-published boundary data is made available for public use; if
SIH organizers or MoSPI require a specific licensed source, swap this file with
an equivalent states-level GeoJSON keeping the same schema
(`FeatureCollection`, `properties.st_nm`).

Reference (licensed alternative): India boundaries by the DataMeet India
community — https://github.com/datameet/maps (CC BY 4.0) — note it is
pre-2019 (no Ladakh separate; merged into Jammu & Kashmir), so it would
require a Ladakh split to match our dataset.

State names verified to match the frozen PARAKH dataset's 36 state values
exactly — zero name-mapping needed at render time.
