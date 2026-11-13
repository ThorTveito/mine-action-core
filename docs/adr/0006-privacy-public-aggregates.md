# 0006: Public aggregates, private records, no victim names

**Status:** accepted

## Context
Mine action data includes victims, informants and exact locations of reports. Publishing hazard
data helps communities stay safe; publishing personal data can put people at risk.

## Decision
- Victims are stored without names or exact dates of birth: sex, age, outcome, deminer flag.
- Field reports and accidents are visible only to their author and to staff; asking for one you
  may not see returns 404, so ids do not leak.
- Public endpoints (dashboard, annual report, audit log, hazards) return aggregates only. The
  audit log hides field-report, accident and user history from callers without the matching
  permission. Hazards created from a report carry only the report code, never its text or the
  reporter's name.
- Tests assert that public responses contain no names and no report text.

## Consequences
Every new public endpoint needs the same scrutiny; AGENTS.md says so.
