# Field reports

Surveyors in the field register what they find on a phone; IM staff review each report and
turn it into hazard data or close it. Code: [`backend/app/routers/field_reports.py`](../backend/app/routers/field_reports.py),
[`frontend/src/FieldPage.tsx`](../frontend/src/FieldPage.tsx), [`frontend/src/outbox.ts`](../frontend/src/outbox.ts).

## Who can do what

| Role | Submit | See reports | Review (accept / reject) |
|------|--------|-------------|--------------------------|
| surveyor | yes | **own only** | no |
| editor (IM officer) | yes | all | yes |
| qa_officer | no | all | no |
| admin | yes | all | yes |
| viewer / anonymous | no | no | no |

Field reports are **not public**, unlike the hazard map: they are unverified and may name
informants. Asking for someone else's report returns 404, not 403, so report ids don't leak.

## What a report holds

Finding type (`item_found`, `suspected_area`, `accident`, `other`), item category (required when
an item was found) and quantity, source (`direct_observation`, `local_informant`, `authority`),
free text, the time it was observed, a GPS point with its accuracy, and who reported it.
Validation rejects coordinates out of range, timestamps more than 10 minutes in the future
(a wrong device clock), and an item finding without an item.

## Working offline

Coverage is poor where mines are. The form never loses a report:

1. The device generates a `client_id` (UUID) for every report.
2. If there is no connection, or the server fails, the report goes into an **outbox** in the
   browser's storage and the user is told so.
3. The outbox is sent automatically when the app opens and whenever the connection returns
   (`online` event), or on demand with **Send now**.
4. The server treats a repeated `client_id` as the same report (returns it with 200), so a
   retry after a lost response never creates a duplicate. Another user reusing the id gets 409.
5. Reports the server refuses (validation) stay in the outbox marked for attention, instead of
   being retried forever; expired logins pause sending until the user logs in again.

Limits: the outbox lives in that browser on that device. The app shell itself is not cached
for offline start (no service worker yet), so the page must be opened while online once.

## Review (triage)

For each submitted report, staff see the **hazards within 500 m** (nearest first, with distance
and whether the point is inside). Then:

- **Link** to an existing hazard (the report is evidence for it), or
- **Create SHA**: a new *suspected* hazard area, a geodesic circle of the chosen radius around
  the point (default 50 m). The hazard class follows the item (AP mine → anti-personnel, ...),
  and the region is taken from the nearest existing hazard. Spatial errors the new area
  causes (for example an overlap) are returned as warnings, or
- **Record an accident** (for accident reports): victims by sex, age and outcome, and the activity
  at the time. The accident is linked to the hazard containing the point or the nearest within
  500 m; the report's own text stays in the report, or
- **Reject** with a reason (duplicate, not credible, ...).

Decisions are final (409 on a second decision) and audited with the reviewer, and the reporter
sees the outcome in "My reports".

**A finding inside a released hazard** is flagged at review and in the accept response. Released
land should be clean, so this points to residual contamination or a QA failure and must be
investigated. The data model keeps `released` terminal, so re-opening is a follow-up decision
outside the app for now.

## Demo data

`make seed` adds six reports from `surveyor`: one inside a released hazard, one just outside a
confirmed hazard, a suspected area far from anything, an accident, one already accepted (linked)
and one rejected as a duplicate.
