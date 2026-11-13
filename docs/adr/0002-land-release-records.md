# 0002: Land release as method-tagged records under tasks

**Status:** accepted

## Context
IMAS 07.11 distinguishes land **cancelled** (non-technical survey), **reduced** (technical
survey) and **cleared**. Reporting only "cleared area" hides the cheapest and most common way
land is released, and makes survey work invisible.

## Decision
Every land-release record carries a `release_method` that is **derived from its task type**
(NTS → cancelled, TS → reduced, clearance → cleared; verification releases nothing). A hazard's
outstanding area is its area minus the land released inside it, and the total released can never
exceed the hazard's area. The existing `clearance_records` table was extended (with a backfill
migration) rather than renamed, to keep the API stable.

## Alternatives
- Splitting hazard polygons on every reduction (what a full GIS workflow does): more faithful,
  far more complex, and needs polygon editing in the UI. Left for later.
- A separate table per method: three nearly identical tables and harder aggregation.

## Consequences
Dashboards and the annual report can show release by method and year; the status of a hazard
(released or not) stays a separate, rule-governed decision.
