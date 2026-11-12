# Glossary

Terms follow common mine action usage (IMAS-style). This project is a
simplified model for demonstration, not a statement of any standard.
Keep this file in sync with the enums in `backend/app/models.py`.

| Term | Meaning in this project |
|------|-------------------------|
| **Hazard** | An area known or suspected to contain explosive ordnance. The central record. |
| **SHA** (Suspected Hazardous Area) | Area where contamination is suspected but not confirmed. |
| **CHA** (Confirmed Hazardous Area) | Area where contamination has been confirmed by evidence. |
| **Hazard class** | Dominant threat: `anti_personnel`, `anti_vehicle`, `mixed`, `cluster_munition`, `uxo`. |
| **Hazard status** | `suspected` → `confirmed` → `in_clearance` → `released`; or `cancelled` (found not hazardous). `in_clearance` may fall back to `confirmed`; `released` and `cancelled` are terminal. New hazards start as `suspected` or `confirmed`. |
| **Release preconditions** | A hazard can be `released` only if it has a completed clearance task, no planned/active/suspended tasks, a passing latest QA inspection on every completed clearance task, and no error-level spatial issue. |
| **Task** | A unit of planned work against one hazard: `survey`, `clearance` or `verification`. |
| **Task status** | `planned`, `active`, `suspended`, `completed`, `cancelled`. |
| **Clearance record** | A dated report of work done under a task: area cleared (m²), items found/destroyed, team. |
| **Release** | Handing land back as safe to use after clearance and verification. |
| **Region** | Fictional first-level administrative unit of Karvonia. |
| **Audit trail** | Append-only history of changes: entity, action, old/new values, and source (`api`, `import:<id>`, `seed`). |
| **Duplicate / overlap** | On import, polygons with IoU >= 0.9 against an existing or earlier hazard are duplicates; >= 10% overlap of the smaller polygon is a warning. |
| **Release percent** | Released area divided by contaminated area (everything not cancelled). |
| **Role** | `viewer` (read only), `surveyor` (field staff: submits field reports, sees only their own), `editor` (enters data and imports; the IM officer), `qa_officer` (records inspections, releases hazards), `admin` (everything, including deletes and users). Reads are public. |
| **QA / QC inspection** | A sampling inspection of cleared ground by a task's operator (QC) or independently (QA): sample area, residual items found, `pass` or `fail`. An inspection that found residual items cannot pass. |
| **Topology (spatial checks)** | Rules between and within polygons: `overlap`, `minor_overlap`, `release_conflict`, `gap` (near miss), `sliver`, `tiny_area`, `tiny_hole`, `spike`, `duplicate_vertices`. See `docs/topology.md`. |
| **Field report** | A finding registered in the field (item found, suspected area, accident, other) with a GPS point; reviewed by staff into a new SHA, a link to an existing hazard, or a rejection. |
| **Outbox** | Reports saved on the device while offline, sent automatically when the connection returns. |
| **Cluster** | A contiguous block of hazards connected by shared boundaries, usually planned as one operation. |
| **Terrain (3D)** | Relief from elevation data (DEM) shown on the map; unrelated to the topology rules above. |
| **Karvonia** | The fictional country all synthetic data belongs to. |

Not modelled yet: accident and victim records, reduction and cancellation by
survey, finer-grained roles per organisation.
