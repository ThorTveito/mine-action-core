# Prioritisation

Every open hazard (suspected, confirmed, in clearance) gets a **0–100 priority score**, built
from five components that are returned with the score so a ranking can be argued with. Code:
[`backend/app/priority.py`](../backend/app/priority.py). Endpoint: `GET /api/priorities`
(public), weights at `GET /api/priorities/weights`.

| Component | Weight | Factor (0–1) | Why it matters |
|-----------|-------:|--------------|----------------|
| Casualties nearby | 35 | victims within 2 km in the last 5 years, full at 8 | People are being hurt: the strongest signal of risk |
| Recent field reports | 15 | non-rejected reports within 1 km in the last 12 months, full at 3 | The land is in use and people see items |
| Threat type | 20 | AP 1.0, submunitions 0.9, mixed 0.8, UXO 0.6, AV 0.5 | Anti-personnel mines and submunitions threaten civilians most |
| Evidence | 15 | confirmed / in clearance 1.0, suspected 0.5 | Confirmed contamination outranks suspicion |
| Size | 15 | 1 − area / 50 ha | Small areas are released quickly: a quick win frees land sooner |

Distances are geodesic (PostGIS `geography`), with an index-friendly degree prefilter.

## Limits, on purpose

- **The weights are illustrative.** Real programmes agree prioritisation criteria nationally,
  with the national authority and affected communities, and include things this demo does not
  model: blocked access to water, schools, roads and farmland, development plans, returnee
  movements.
- **Casualty data is incomplete everywhere.** A hazard with no recorded accidents is not safe;
  the score reflects recorded evidence only.
- **Size cuts both ways.** Small areas are quick wins, but large areas may block more land use.
  Adjust the weight to the programme's strategy.

The point is the *mechanism*: a score that is reproducible, explained per component, and easy
to retune, instead of an opaque ranking.
