# Sample import files

Synthetic data for trying the import pipeline (Import tab, or `POST /api/imports/hazards`).
They assume the database was loaded with `make seed` (the demo file refers to seeded
hazard codes such as `KRV-HAZ-00001`).

| File | Source CRS | What it shows |
|------|------------|---------------|
| `hazards_import_demo.csv` | `EPSG:4326` | 2 valid new rows, 1 valid status update, and rejections for: self-intersecting ring, projected coordinates without a CRS, duplicate inside the file, duplicate of an existing hazard, invalid enum value, illegal status transitions, unknown code. One row is accepted with an overlap warning. |
| `hazards_utm_32632.csv` | `EPSG:32632` | Clean rows in UTM zone 32N metres, reprojected to WGS 84 on import. |
| `hazards_topology_warnings.csv` | `EPSG:4326` | Rows that are accepted but carry topology warnings (`topology_sliver`, `topology_gap`, `topology_tiny_area`). |

Importing needs an editor or admin login (see the login form for demo accounts).
Try a dry run first (the default), then commit. With `on_error=abort`, one bad row
blocks the whole file.
