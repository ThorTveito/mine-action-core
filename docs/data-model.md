# Data model

PostgreSQL 16 with PostGIS. All geometry is EPSG:4326; areas, lengths and distances are
computed on `geography` (metres). Migrations are hand-written and reversible
([`backend/alembic/versions/`](../backend/alembic/versions/)).

```mermaid
erDiagram
    ADMIN_AREAS ||..o{ HAZARDS : "contains (by geometry)"
    HAZARDS ||--o{ TASKS : has
    TASKS ||--o{ CLEARANCE_RECORDS : "releases land"
    TASKS ||--o{ QA_INSPECTIONS : "is inspected"
    HAZARDS |o--o{ FIELD_REPORTS : "linked after triage"
    HAZARDS |o--o{ ACCIDENTS : "nearest within 500 m"
    FIELD_REPORTS |o--o| ACCIDENTS : "may become"
    ACCIDENTS ||--o{ VICTIMS : has
    ADMIN_AREAS ||..o{ RISK_EDUCATION_SESSIONS : "contains"
    USERS ||..o{ AUDIT_LOG : "actor of"

    HAZARDS {
        int id PK
        string code "KRV-HAZ-00001"
        string hazard_type "SHA | CHA"
        string hazard_class "anti_personnel | ... | uxo"
        string status "suspected | confirmed | in_clearance | released | cancelled"
        string region
        multipolygon geom "GiST index"
        float area_m2 "geodesic"
    }
    TASKS {
        int id PK
        string code "KRV-TSK-00001"
        string task_type "survey | technical_survey | clearance | verification"
        string status "planned | active | suspended | completed | cancelled"
        string organisation
    }
    CLEARANCE_RECORDS {
        int id PK
        date record_date
        float area_cleared_m2 "area released"
        string release_method "cancelled | reduced | cleared"
        int items_found
        int items_destroyed
    }
    QA_INSPECTIONS {
        int id PK
        string inspection_type "qa | qc"
        string outcome "pass | fail"
        int residual_items_found
    }
    FIELD_REPORTS {
        int id PK
        string client_id "unique: idempotent resend"
        string finding_type
        point location "GiST index"
        string status "submitted | accepted | rejected"
    }
    ACCIDENTS {
        int id PK
        date occurred_on
        point location
        string activity
    }
    VICTIMS {
        int id PK
        string sex "female | male | unknown"
        int age "nullable; no names"
        string outcome "killed | injured"
        bool is_deminer
    }
    RISK_EDUCATION_SESSIONS {
        int id PK
        date held_on
        point location
        int girls
        int boys
        int women
        int men
    }
    ADMIN_AREAS {
        int id PK
        string name
        multipolygon geom
    }
    AUDIT_LOG {
        int id PK
        string entity_type
        string action
        jsonb changes "old and new values"
        string source "api | import:id | field_report:code | seed"
        string actor
    }
```

## Integrity rules worth knowing

- Enums are strings with CHECK constraints (simple, reversible migrations).
- A land-release record's method must match its task type; verification releases nothing; the
  land released inside a hazard can never exceed its area (1% tolerance).
- An inspection that found residual items cannot pass (CHECK constraint and API validation).
- `field_reports.client_id` is unique, which makes offline resends idempotent.
- Audit rows are append-only and never cascade-deleted.
