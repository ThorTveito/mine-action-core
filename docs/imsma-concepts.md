# IMSMA / IMAS concepts in this project

This project is **inspired by** GICHD's Information Management System for Mine Action (IMSMA
Core) and the International Mine Action Standards (IMAS). It does not copy IMSMA's schema, forms
or interface, and it is not affiliated with GICHD. IMSMA Core itself runs on Esri's ArcGIS
platform; this project rebuilds comparable *concepts* on an open-source stack.

IMAS numbers below refer to the standards as I know them; check the current editions at
[mineactionstandards.org](https://www.mineactionstandards.org) before relying on a reference.

| Concept | Standard / source | In this project | Where |
|---------|-------------------|-----------------|-------|
| **Hazardous area**: suspected (SHA) and confirmed (CHA) | IMAS 04.10 (glossary), 08.10 | `hazards` with type SHA/CHA, threat class, geometry and geodesic area | `models.Hazard` |
| **Land release**: cancel, reduce, clear | IMAS 07.11 | Every land-release record carries a method that follows its task: non-technical survey cancels, technical survey reduces, clearance clears. Reported separately everywhere | `models.ReleaseMethod`, `analytics.land_release` |
| **Non-technical survey (NTS)** | IMAS 08.10 | `survey` tasks; may cancel land, or lead to a confirmed hazard | `TaskType.SURVEY` |
| **Technical survey (TS)** | IMAS 08.20 | `technical_survey` tasks; reduce land; can lead to release without clearance | `TaskType.TECHNICAL_SURVEY` |
| **Clearance** | IMAS 09.10 | `clearance` tasks with dated records of area cleared and items found/destroyed | `ClearanceRecord` |
| **Quality management** (QA/QC, sampling) | IMAS 07.12 | QA/QC inspections with sampled area and residual items; a failed latest inspection blocks release | `QaInspection`, `rules.check_release_preconditions` |
| **Release decision** | IMAS 07.11 | A hazard is released only after a completed TS or clearance task, no open tasks, passing QA on every land-release task, and no spatial errors; only a QA officer may do it | `rules.py`, `auth.py` |
| **Hazard reduction / activity reporting** | IMSMA data model | Tasks per hazard with status, organisation and dates; progress records under each task | `Task`, `ClearanceRecord` |
| **Accidents and victims** | IMAS 13.10 (victim assistance), Landmine Monitor reporting | Accidents linked to the nearest hazard; victims by sex, age, outcome, deminer flag; **no names** | `Accident`, `Victim`, `analytics.casualties` |
| **Sex- and age-disaggregated data (SADD)** | Mine action reporting practice | Casualty grid (female/male/unknown × child/adult/unknown) and EORE counts (girls/boys/women/men) | Dashboard, annual report |
| **Explosive ordnance risk education (EORE)** | IMAS 12.10 | Sessions with location, organisation and audience by sex and age | `RiskEducationSession` |
| **Field data collection** | IMSMA Core uses mobile forms (Survey123) | Field reports from a phone with GPS, offline outbox with idempotent resend | `field_reports`, `frontend/src/outbox.ts` |
| **Data review / approval** before data enters the database | IMSMA workflow | Field-report triage: new SHA, link to a hazard, record an accident, or reject with a reason | `routers/field_reports.py` |
| **Gazetteer / administrative areas** | IMSMA "locations" | Admin-area polygons; region assigned by point-in-polygon; mismatches flagged | `AdminArea`, `gazetteer.py` |
| **Data quality** | IM practice, IMAS 05.10 | Geometry validation, import rejection reports, spatial (topology) checks, audit trail | `geo.py`, `importer.py`, `topology.py`, `audit.py` |
| **Prioritisation** | National mine action strategies | Explainable score from casualties nearby, recent reports, threat, evidence and size | `priority.py`, `docs/prioritisation.md` |
| **Transparency reporting** | APMBC Article 7 | Annual report: remaining contamination by area, land released by method, items destroyed, casualties (SADD), EORE, QA | `/api/reports/annual`, Annual report tab |
| **Operators / organisations** | IMSMA data model | Organisation on tasks; operator performance on the dashboard | Dashboard "Operators" |

## Deliberately left out

- Victim assistance services and follow-up (IMAS 13.10 covers far more than casualty records).
- Explosive ordnance by detailed type per record (only categories and counts).
- Stockpile destruction, mine-free declarations, polygon editing in the browser, multi-language
  forms, and the national-authority accreditation of operators.
