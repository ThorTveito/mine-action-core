# 0004: JWT and role permissions with separation of duties

**Status:** accepted

## Context
Quality management only means something if the person who clears land cannot also sign it off.
The demo must also be browsable by anyone without an account.

## Decision
Stateless JWT (HS256) with scrypt password hashing from the standard library. Roles map to
permissions in one table (`ROLE_PERMISSIONS`): editors write and import; QA officers inspect and
release; surveyors only report; admins do everything. Reads of hazard data are public; writes
need a login. Login attempts are throttled per username and address.

## Alternatives
An external identity provider (OIDC) is the right choice for a real deployment; it was left out
to keep the demo self-contained.

## Consequences
The frontend mirrors the permission table only as a UI hint; the API is the authority and every
permission is tested. Throttling is in memory, so multi-instance deployments need it at the proxy.
