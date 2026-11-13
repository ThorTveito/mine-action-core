# 0005: Offline field reports with client-generated ids

**Status:** accepted

## Context
Contaminated areas often have no signal. A report that fails to send must not be lost, and a
retry after a lost response must not create a duplicate.

## Decision
The device generates a UUID `client_id` per report. Unsent reports wait in a local outbox and
are resent on load, when the browser comes back online, or on demand. The server treats a
repeated `client_id` from the same user as the same report (200 with the stored record), and from
another user as a conflict (409). Reports the server refuses (validation) are parked for the
user instead of retried forever.

## Alternatives
Background Sync / a service worker would also send while the app is closed; it was left for
later because it adds an install step and browser-specific behaviour.

## Consequences
The outbox can retry blindly and is unit-tested. The app shell must be opened online once.
