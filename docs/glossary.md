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
| **Release preconditions** | A hazard can be `released` only if it has a completed clearance task and no planned/active/suspended tasks. |
| **Task** | A unit of planned work against one hazard: `survey`, `clearance` or `verification`. |
| **Task status** | `planned`, `active`, `suspended`, `completed`, `cancelled`. |
| **Clearance record** | A dated report of work done under a task: area cleared (m²), items found/destroyed, team. |
| **Release** | Handing land back as safe to use after clearance and verification. |
| **Region** | Fictional first-level administrative unit of Karvonia. |
| **Audit trail** | Append-only history of changes: entity, action, old/new values, and source (`api`, `import:<id>`, `seed`). |
| **Duplicate / overlap** | On import, polygons with IoU >= 0.9 against an existing or earlier hazard are duplicates; >= 10% overlap of the smaller polygon is a warning. |
| **Release percent** | Released area divided by contaminated area (everything not cancelled). |
| **Karvonia** | The fictional country all synthetic data belongs to. |

Planned for later tiers: QA/QC, accident and victim records, reduction and
cancellation by survey, user identity on audit entries.
