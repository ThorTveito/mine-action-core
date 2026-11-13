# 0003: One rule module for every entry point

**Status:** accepted

## Context
Data enters through the REST API, bulk import and field-report triage. If each path implements
its own checks, one of them becomes a back door (for example, importing a hazard straight to
"released").

## Decision
Lifecycle transitions, release preconditions (completed task, QA, spatial errors) and the
permission check for releasing live in `rules.py` / `auth.py` and are called by every path.
Import validation is side-effect free, which is what makes dry runs trustworthy.

## Consequences
A new rule is written once and tested once per entry point. The seed is the only code that
bypasses the rules, on purpose, to create historical states.
